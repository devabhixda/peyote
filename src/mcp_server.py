import os
import asyncio
from dotenv import load_dotenv
from supabase import create_client, Client
from openai import OpenAI
from mcp.server.models import InitializationOptions
from mcp.server import NotificationOptions, Server
from mcp.server.stdio import stdio_server
from mcp import types

# -- SETUP --
# Load environment variables from .env file
load_dotenv()

# Initialize clients
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_SERVICE_KEY")
openai_api_key = os.getenv("OPENAI_API_KEY")

if not all([supabase_url, supabase_key, openai_api_key]):
    raise ValueError("Supabase URL/Key or OpenAI API Key is missing from .env file")

supabase: Client = create_client(supabase_url, supabase_key)
openai_client = OpenAI(api_key=openai_api_key)

# -- CONFIGURATION --
EMBEDDING_MODEL = "text-embedding-3-small"
MATCH_COUNT = 5  # Number of code chunks to retrieve for context
SIMILARITY_THRESHOLD = 0.35  # Minimum similarity score (0-1) for results

# Initialize MCP server
server = Server("peyote-code-context")

def construct_augmented_prompt(original_code, context_chunks):
    """Constructs a prompt for the LLM, combining original code with retrieved context."""
    
    context_str = "\n---\n".join([chunk['content'] for chunk in context_chunks])
    
    prompt = f"""You are an expert AI programming assistant.
    A user is writing the following code and needs a completion.

    <USER_CODE>
    {original_code}
    </USER_CODE>

    To help you, here is some additional relevant context from other files in the user's repository:

    <CONTEXT>
    {context_str}
    </CONTEXT>

    Based on the user's code and the provided context, complete the user's code.
    Only provide the code completion itself, without any introductory text.
    """
    return prompt

async def retrieve_context(code_snippet: str):
    """Retrieves relevant code context from the vector database."""
    try:
        # Generate an embedding for the code
        response = openai_client.embeddings.create(input=code_snippet, model=EMBEDDING_MODEL)
        query_embedding = response.data[0].embedding
        
        # Query Supabase to find similar code chunks
        rpc_params = {
            'query_embedding': query_embedding,
            'match_count': MATCH_COUNT
        }
        retrieved_chunks_response = supabase.rpc('match_code_chunks', rpc_params).execute()
        
        if not retrieved_chunks_response.data:
            return []
        
        retrieved_chunks = retrieved_chunks_response.data
        
        # Filter out chunks with low similarity and data-heavy content
        filtered_chunks = []
        for chunk in retrieved_chunks:
            similarity = chunk.get('similarity', 0)
            content = chunk.get('content', '')
            
            # Skip if similarity is too low
            if similarity < SIMILARITY_THRESHOLD:
                continue
            
            # Skip if content looks like hex/data arrays (more than 20% hex patterns)
            hex_pattern_count = content.count('0x')
            if hex_pattern_count > 10 and len(content) > 0:
                hex_ratio = hex_pattern_count / (len(content) / 100)
                if hex_ratio > 0.2:  # More than 20% of content is hex patterns
                    continue
            
            filtered_chunks.append(chunk)
        
        return filtered_chunks
    except Exception as e:
        raise Exception(f"Error retrieving context: {e}")

@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """List available tools."""
    return [
        types.Tool(
            name="get_code_context",
            description="Retrieves relevant code context from the codebase based on a code snippet. "
                       "Uses semantic search to find similar code chunks that can help with code completion.",
            inputSchema={
                "type": "object",
                "properties": {
                    "code_snippet": {
                        "type": "string",
                        "description": "The code snippet to find context for"
                    }
                },
                "required": ["code_snippet"]
            }
        ),
        types.Tool(
            name="augment_prompt",
            description="Augments a code completion prompt with relevant context from the codebase. "
                       "Returns a complete prompt that can be used with an LLM.",
            inputSchema={
                "type": "object",
                "properties": {
                    "code_snippet": {
                        "type": "string",
                        "description": "The code snippet to augment with context"
                    }
                },
                "required": ["code_snippet"]
            }
        )
    ]

@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict | None
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """Handle tool execution requests."""
    
    if not arguments:
        raise ValueError("Missing arguments")
    
    code_snippet = arguments.get("code_snippet")
    if not code_snippet:
        raise ValueError("Missing required argument: code_snippet")
    
    if name == "get_code_context":
        try:
            retrieved_chunks = await retrieve_context(code_snippet)
            
            if not retrieved_chunks:
                return [
                    types.TextContent(
                        type="text",
                        text="No relevant code context found."
                    )
                ]
            
            # Format the context for display
            # The match_code_chunks function returns: id, file_path, content, similarity
            context_text = "# Retrieved Code Context\n\n"
            for i, chunk in enumerate(retrieved_chunks, 1):
                context_text += f"## Context {i}\n"
                context_text += f"**File:** {chunk.get('file_path', 'Unknown')}\n"
                context_text += f"**Similarity:** {chunk.get('similarity', 'N/A'):.4f}\n\n"
                context_text += f"```\n{chunk.get('content', '')}\n```\n\n"
            
            return [
                types.TextContent(
                    type="text",
                    text=context_text
                )
            ]
        except Exception as e:
            return [
                types.TextContent(
                    type="text",
                    text=f"Error retrieving context: {str(e)}"
                )
            ]
    
    elif name == "augment_prompt":
        try:
            retrieved_chunks = await retrieve_context(code_snippet)
            augmented_prompt = construct_augmented_prompt(code_snippet, retrieved_chunks)
            
            return [
                types.TextContent(
                    type="text",
                    text=augmented_prompt
                )
            ]
        except Exception as e:
            return [
                types.TextContent(
                    type="text",
                    text=f"Error augmenting prompt: {str(e)}"
                )
            ]
    
    else:
        raise ValueError(f"Unknown tool: {name}")

async def main():
    """Main entry point for the MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="peyote-code-context",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )

if __name__ == "__main__":
    asyncio.run(main())