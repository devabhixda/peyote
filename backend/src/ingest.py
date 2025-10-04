import os
import git
import tempfile
from dotenv import load_dotenv
from supabase import create_client, Client
from openai import OpenAI
from langchain.text_splitter import RecursiveCharacterTextSplitter
import time
from flask import Flask, request, jsonify
from threading import Thread
import traceback
import logging
from datadog import initialize, api

# -- SETUP --
load_dotenv()
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_SERVICE_KEY")
openai_api_key = os.getenv("OPENAI_API_KEY")

# Datadog configuration
dd_api_key = os.getenv("DD_API_KEY")
dd_app_key = os.getenv("DD_APP_KEY")
dd_service_name = os.getenv("DD_SERVICE_NAME", "peyote-ingest")
dd_env = os.getenv("DD_ENV", "production")
dd_site = os.getenv("DD_SITE", "datadoghq.com")

# Initialize Datadog metrics (HTTP API only - no local agent required)
dd_metrics_enabled = False

if dd_api_key:
    try:
        # Initialize Datadog API for metrics (uses HTTP API directly to cloud)
        initialize(
            api_key=dd_api_key, 
            app_key=dd_app_key,
            api_host=f"https://api.{dd_site}",
            statsd_host=None,  # Disable UDP statsd to avoid connection errors
            statsd_port=None
        )
        dd_metrics_enabled = True
        print(f"✓ Datadog metrics initialized (cloud-only, no agent required)")
        print(f"  Service: {dd_service_name}, Environment: {dd_env}")
            
    except Exception as e:
        print(f"⚠ Warning: Failed to initialize Datadog: {e}")
else:
    print("⚠ Warning: DD_API_KEY not found. Datadog monitoring will be disabled.")

# Create custom statsd wrapper that uses API instead of UDP
class DatadogMetrics:
    """Wrapper for Datadog metrics using HTTP API instead of statsd UDP."""
    
    def __init__(self, enabled=False, service_name="", env=""):
        self.enabled = enabled
        self.service_name = service_name
        self.env = env
        self.default_tags = [f'service:{service_name}', f'env:{env}']
    
    def _send_metric(self, metric_name, metric_type, value, tags=None):
        if not self.enabled:
            return
        try:
            all_tags = self.default_tags + (tags or [])
            # Use Datadog HTTP API to send metrics
            api.Metric.send(
                metric=f"{self.service_name}.{metric_name}",
                points=value,
                type=metric_type,
                tags=all_tags
            )
        except Exception as e:
            # Silently fail - don't disrupt application
            pass
    
    def increment(self, metric_name, value=1, tags=None):
        self._send_metric(metric_name, 'count', value, tags)
    
    def histogram(self, metric_name, value, tags=None):
        self._send_metric(metric_name, 'gauge', value, tags)
    
    def gauge(self, metric_name, value, tags=None):
        self._send_metric(metric_name, 'gauge', value, tags)
    
    def timing(self, metric_name, value, tags=None):
        self._send_metric(metric_name, 'gauge', value, tags)

# Initialize custom metrics client
statsd = DatadogMetrics(enabled=dd_metrics_enabled, service_name=dd_service_name, env=dd_env)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

if not all([supabase_url, supabase_key, openai_api_key]):
    raise ValueError("Supabase URL/Key or OpenAI API Key is missing from .env file")

supabase: Client = create_client(supabase_url, supabase_key)
openai_client = OpenAI(api_key=openai_api_key)

# -- FLASK APP --
app = Flask(__name__)

# -- CONFIGURATION --
EMBEDDING_MODEL = "text-embedding-3-small"
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 100
BATCH_SIZE = 100

INCLUDE_EXTENSIONS = ['.py', '.js', '.ts', '.md', '.go', '.rs', '.java', '.c', '.cpp', '.h', '.hpp']
IGNORE_DIRECTORIES = ['.git', 'node_modules', 'dist', 'build', '__pycache__']
IGNORE_FILES = ['package-lock.json', 'yarn.lock']

def clone_repo(repo_url, temp_dir):
    """Clones a Git repository into a temporary directory."""
    logger.info(f"Cloning repository from {repo_url}...")
    
    start_time = time.time()
    try:
        git.Repo.clone_from(repo_url, temp_dir)
        duration = time.time() - start_time
        
        # Send metrics to Datadog
        statsd.increment('repo.clone.success', tags=[f'repo:{repo_url}'])
        statsd.histogram('repo.clone.duration', duration, tags=[f'repo:{repo_url}'])
        
        logger.info("Repository cloned successfully.")
        return temp_dir
    except git.GitCommandError as e:
        duration = time.time() - start_time
        error_msg = str(e)
        
        # Send error metrics to Datadog
        statsd.increment('repo.clone.error', tags=[f'repo:{repo_url}', f'error_type:git_error'])
        statsd.histogram('repo.clone.duration', duration, tags=[f'repo:{repo_url}', 'status:failed'])
        
        logger.error(f"Error cloning repository: {error_msg}")
        return None

def get_repo_metadata(repo_path):
    """Gets metadata about the git repository."""
    repo = git.Repo(repo_path)
    commit_hash = repo.head.commit.hexsha
    repo_name = repo.remotes.origin.url.split('/')[-1].replace('.git', '')
    return {"repo_name": repo_name, "commit_hash": commit_hash}

def get_language_from_extension(file_path):
    """Infers the programming language from the file extension."""
    ext_to_lang = {
        '.py': 'python', '.js': 'javascript', '.ts': 'typescript',
        '.md': 'markdown', '.go': 'go', '.rs': 'rust',
        '.java': 'java', '.c': 'c', '.cpp': 'c++', '.h': 'c++', '.hpp': 'c++'
    }
    _, ext = os.path.splitext(file_path)
    return ext_to_lang.get(ext, None)

def send_completion_email(user_email, repo_url, status, error_message=None):
    """Sends email notification via Supabase Edge Function."""
    try:
        edge_function_name = "resend"
        payload = {
            "email": user_email,
            "repo_url": repo_url,
            "status": status,
            "error_message": error_message
        }
        
        response = supabase.functions.invoke(edge_function_name, invoke_options={"body": payload})
        
        # Send success metric
        statsd.increment('email.notification.sent', tags=[f'status:{status}', f'repo:{repo_url}'])
        
        logger.info(f"Email notification sent to {user_email} - Status: {status}")
        return response
    except Exception as e:
        error_msg = str(e)
        
        # Send error metric
        statsd.increment('email.notification.error', tags=[f'status:{status}', f'repo:{repo_url}'])
        
        logger.error(f"Error sending email notification: {error_msg}")
        return None

def process_and_insert_batch(batch):
    """Processes a batch of chunks: gets embeddings and inserts into Supabase."""
    if not batch:
        return

    batch_start_time = time.time()
    
    try:
        # 1. Get all contents from the batch to send to OpenAI
        contents = [item['content'] for item in batch]
        
        # 2. Get embeddings for the entire batch in one API call
        embedding_start = time.time()
        response = openai_client.embeddings.create(input=contents, model=EMBEDDING_MODEL)
        embeddings = [data.embedding for data in response.data]
        embedding_duration = time.time() - embedding_start
        
        # Send embedding metrics
        statsd.histogram('openai.embeddings.duration', embedding_duration, tags=[f'model:{EMBEDDING_MODEL}', f'num_inputs:{len(contents)}'])
        statsd.increment('openai.embeddings.success', tags=[f'model:{EMBEDDING_MODEL}'])

        # 3. Prepare records for Supabase insertion
        records_to_insert = []
        for i, item in enumerate(batch):
            records_to_insert.append({
                'file_path': item['file_path'],
                'content': item['content'],
                'embedding': embeddings[i],
                'metadata': item['metadata']
            })
            
        # 4. Insert all records into Supabase in one API call
        insert_start = time.time()
        supabase.table("code_chunks").insert(records_to_insert).execute()
        insert_duration = time.time() - insert_start
        
        # Send insert metrics
        statsd.histogram('supabase.insert.duration', insert_duration, tags=['table:code_chunks', f'num_records:{len(records_to_insert)}'])
        statsd.increment('supabase.insert.success', tags=['table:code_chunks'])
        
        batch_duration = time.time() - batch_start_time
        logger.info(f"Successfully ingested batch of {len(batch)} chunks in {batch_duration:.2f}s")
        
        # Send batch metrics
        statsd.histogram('batch.process.duration', batch_duration, tags=[f'batch_size:{len(batch)}'])
        statsd.increment('batch.process.success', tags=[f'batch_size:{len(batch)}'])
        
    except Exception as e:
        error_msg = str(e)
        batch_duration = time.time() - batch_start_time
        
        # Send error metrics
        statsd.histogram('batch.process.duration', batch_duration, tags=[f'batch_size:{len(batch)}', 'status:failed'])
        statsd.increment('batch.process.error', tags=[f'batch_size:{len(batch)}'])
        
        logger.error(f"Error processing batch: {error_msg}")
        raise


def process_repository(repo_path, repo_url=None):
    """Walks through the repository, processes files, and ingests them in batches."""
    repo_meta = get_repo_metadata(repo_path)
    if repo_url:
        repo_meta['repo_url'] = repo_url
    
    logger.info(f"Processing repository: {repo_meta.get('repo_name', 'N/A')}")
    
    # Send metric for repository processing start
    statsd.increment('repo.process.started', tags=[f'repo:{repo_meta.get("repo_name", "unknown")}'])
    
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
    batch = []
    total_files = 0
    total_chunks = 0

    for root, dirs, files in os.walk(repo_path, topdown=True):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRECTORIES]
        
        for file in files:
            file_path = os.path.join(root, file)
            
            if file in IGNORE_FILES or not any(file.endswith(ext) for ext in INCLUDE_EXTENSIONS):
                continue

            try:
                with open(file_path, "r", encoding='utf-8') as f:
                    content = f.read()
                
                chunks = text_splitter.split_text(content)
                language = get_language_from_extension(file_path)
                relative_path = file_path.replace(repo_path, '', 1)
                
                total_files += 1
                total_chunks += len(chunks)

                for chunk_content in chunks:
                    batch.append({
                        "file_path": relative_path,
                        "content": chunk_content,
                        "metadata": {**repo_meta, "language": language}
                    })
                    
                    # When batch is full, process it
                    if len(batch) >= BATCH_SIZE:
                        process_and_insert_batch(batch)
                        batch = [] # Reset the batch

            except Exception as e:
                logger.error(f"Error processing file {file_path}: {e}")
                statsd.increment('file.process.error', tags=[f'file:{relative_path}'])

    # Process any remaining chunks in the last batch
    if batch:
        process_and_insert_batch(batch)
    
    logger.info(f"Repository processing complete. Files: {total_files}, Chunks: {total_chunks}")
    
    # Send completion metrics
    statsd.increment('repo.process.completed', tags=[f'repo:{repo_meta.get("repo_name", "unknown")}'])
    statsd.gauge('repo.files.processed', total_files, tags=[f'repo:{repo_meta.get("repo_name", "unknown")}'])
    statsd.gauge('repo.chunks.created', total_chunks, tags=[f'repo:{repo_meta.get("repo_name", "unknown")}'])


def async_ingest_repository(repo_url, user_email):
    """Asynchronously ingests a repository and sends email notification on completion."""
    start_time = time.time()
    try:
        logger.info(f"Starting async ingestion for {repo_url}")
        statsd.increment('ingestion.started', tags=[f'repo:{repo_url}'])
        
        with tempfile.TemporaryDirectory() as temp_dir:
            cloned_repo_path = clone_repo(repo_url, temp_dir)
            if not cloned_repo_path:
                send_completion_email(user_email, repo_url, "failed", "Failed to clone repository")
                statsd.increment('ingestion.failed', tags=[f'repo:{repo_url}', 'reason:clone_failed'])
                return
            
            process_repository(cloned_repo_path, repo_url)
        
        end_time = time.time()
        duration = end_time - start_time
        
        # Send success metrics
        statsd.histogram('ingestion.duration', duration, tags=[f'repo:{repo_url}', 'status:success'])
        statsd.increment('ingestion.completed', tags=[f'repo:{repo_url}', 'status:success'])
        
        logger.info(f"Ingestion complete in {duration:.2f} seconds.")
        send_completion_email(user_email, repo_url, "success")
        
    except Exception as e:
        end_time = time.time()
        duration = end_time - start_time
        error_message = f"{str(e)}\n{traceback.format_exc()}"
        
        # Send error metrics
        statsd.histogram('ingestion.duration', duration, tags=[f'repo:{repo_url}', 'status:failed'])
        statsd.increment('ingestion.failed', tags=[f'repo:{repo_url}', 'reason:processing_error'])
        
        logger.error(f"Error during ingestion: {error_message}")
        send_completion_email(user_email, repo_url, "failed", error_message)

@app.route('/ingest', methods=['POST'])
def ingest_endpoint():
    """API endpoint to trigger repository ingestion."""
    try:
        data = request.get_json()
        
        if not data:
            statsd.increment('api.ingest.error', tags=['error_type:no_data'])
            return jsonify({"error": "No JSON data provided"}), 400
        
        repo_url = data.get('repo_url')
        user_email = data.get('user_email')
        
        if not repo_url:
            statsd.increment('api.ingest.error', tags=['error_type:missing_repo_url'])
            return jsonify({"error": "repo_url is required"}), 400
        
        if not user_email:
            statsd.increment('api.ingest.error', tags=['error_type:missing_user_email'])
            return jsonify({"error": "user_email is required"}), 400
        
        # Start async processing in a background thread
        thread = Thread(target=async_ingest_repository, args=(repo_url, user_email))
        thread.daemon = True
        thread.start()
        
        # Send success metrics
        statsd.increment('api.ingest.accepted', tags=[f'repo:{repo_url}'])
        
        logger.info(f"Ingestion request accepted for {repo_url}")
        
        return jsonify({
            "success": True,
            "message": "Repository ingestion started. You will receive an email when complete.",
            "repo_url": repo_url
        }), 202
        
    except Exception as e:
        error_msg = str(e)
        statsd.increment('api.ingest.error', tags=['error_type:server_error'])
        logger.error(f"Error in ingest endpoint: {error_msg}")
        return jsonify({"error": error_msg}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    statsd.increment('api.health.check')
    return jsonify({"status": "healthy"}), 200

if __name__ == "__main__":
    logger.info("Flask API Server initialized.")
    logger.info(f"Service: {dd_service_name}, Environment: {dd_env}")
    app.run(host='0.0.0.0', port=3000, debug=True)