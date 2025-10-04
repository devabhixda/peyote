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

# -- SETUP --
load_dotenv()
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_SERVICE_KEY")
openai_api_key = os.getenv("OPENAI_API_KEY")

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
    print(f"Cloning repository from {repo_url}...")
    try:
        git.Repo.clone_from(repo_url, temp_dir)
        print("Repository cloned successfully.")
        return temp_dir
    except git.GitCommandError as e:
        print(f"Error cloning repository: {e}")
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
        print(f"Email notification sent to {user_email} - Status: {status}")
        return response
    except Exception as e:
        print(f"Error sending email notification: {e}")
        return None

def process_and_insert_batch(batch):
    """Processes a batch of chunks: gets embeddings and inserts into Supabase."""
    if not batch:
        return

    # 1. Get all contents from the batch to send to OpenAI
    contents = [item['content'] for item in batch]
    
    # 2. Get embeddings for the entire batch in one API call
    response = openai_client.embeddings.create(input=contents, model=EMBEDDING_MODEL)
    embeddings = [data.embedding for data in response.data]

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
    try:
        supabase.table("code_chunks").insert(records_to_insert).execute()
        print(f"  > Successfully ingested batch of {len(batch)} chunks.")
    except Exception as e:
        print(f"Error inserting batch into Supabase: {e}")
        raise


def process_repository(repo_path, repo_url=None):
    """Walks through the repository, processes files, and ingests them in batches."""
    repo_meta = get_repo_metadata(repo_path)
    if repo_url:
        repo_meta['repo_url'] = repo_url
    print(f"Processing repository: {repo_meta.get('repo_name', 'N/A')}")
    
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
    batch = []

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
                print(f"Error processing file {file_path}: {e}")

    # Process any remaining chunks in the last batch
    if batch:
        process_and_insert_batch(batch)

def async_ingest_repository(repo_url, user_email):
    """Asynchronously ingests a repository and sends email notification on completion."""
    start_time = time.time()
    try:
        print(f"Starting async ingestion for {repo_url}")
        with tempfile.TemporaryDirectory() as temp_dir:
            cloned_repo_path = clone_repo(repo_url, temp_dir)
            if not cloned_repo_path:
                send_completion_email(user_email, repo_url, "failed", "Failed to clone repository")
                return
            
            process_repository(cloned_repo_path, repo_url)
        
        end_time = time.time()
        duration = end_time - start_time
        print(f"Ingestion complete in {duration:.2f} seconds.")
        send_completion_email(user_email, repo_url, "success")
        
    except Exception as e:
        error_message = f"{str(e)}\n{traceback.format_exc()}"
        print(f"Error during ingestion: {error_message}")
        send_completion_email(user_email, repo_url, "failed", error_message)

@app.route('/ingest', methods=['POST'])
def ingest_endpoint():
    """API endpoint to trigger repository ingestion."""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400
        
        repo_url = data.get('repo_url')
        user_email = data.get('user_email')
        
        if not repo_url:
            return jsonify({"error": "repo_url is required"}), 400
        
        if not user_email:
            return jsonify({"error": "user_email is required"}), 400
        
        # Start async processing in a background thread
        thread = Thread(target=async_ingest_repository, args=(repo_url, user_email))
        thread.daemon = True
        thread.start()
        
        return jsonify({
            "success": True,
            "message": "Repository ingestion started. You will receive an email when complete.",
            "repo_url": repo_url
        }), 202
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({"status": "healthy"}), 200

if __name__ == "__main__":
    print("Flask API Server initialized.")
    app.run(host='0.0.0.0', port=3000, debug=True)