# Peyote Code Context MCP Server

A Model Context Protocol (MCP) server that provides AI-powered code context retrieval using semantic search. This server integrates with GitHub Copilot and other AI coding assistants to provide relevant code snippets from your codebase.

## Features

- **Semantic Code Search**: Uses OpenAI embeddings to find semantically similar code chunks
- **Vector Database**: Stores code embeddings in Supabase for fast retrieval
- **MCP Integration**: Follows the Model Context Protocol for seamless integration with AI tools
- **Datadog Monitoring**: Comprehensive observability with APM tracing, custom metrics, and error tracking
- **Two Tools**:
  - `get_code_context`: Retrieves relevant code context from the codebase
  - `augment_prompt`: Creates a complete prompt with context for LLM consumption

## Prerequisites

- Python 3.10 or higher
- Supabase account with vector database setup
- OpenAI API key
- (Optional) Datadog account for monitoring and observability

## Installation

1. Clone the repository and navigate to the Server directory:
```bash
cd /Users/devabhi/Projects/Peyote/Server
```

2. Create and activate a virtual environment:
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Create a `.env` file with your credentials:
```env
SUPABASE_URL=your_supabase_url
SUPABASE_SERVICE_KEY=your_supabase_service_key
OPENAI_API_KEY=your_openai_api_key

# Optional: Datadog Monitoring
DD_API_KEY=your_datadog_api_key
DD_APP_KEY=your_datadog_app_key
DD_SERVICE_NAME=peyote-ingest
DD_ENV=production
```

## Usage

### Running the MCP Server

The server uses stdio for communication following the MCP protocol:

```bash
python src/mcp_server.py
```

### Integrating with Cursor

1. Open Cursor Settings (Cmd+Shift+J or Ctrl+Shift+J)
2. Navigate to "Cursor Settings" > "Model Context Protocol"
3. Add a new MCP server configuration by editing the configuration file (usually at `~/.cursor/mcp_settings.json` or through the UI):

```json
{
  "mcpServers": {
    "peyote-code-context": {
      "command": "python",
      "args": ["/Users/devabhi/Projects/Peyote/Server/src/mcp_server.py"],
      "env": {
        "SUPABASE_URL": "your_supabase_url",
        "SUPABASE_SERVICE_KEY": "your_supabase_service_key",
        "OPENAI_API_KEY": "your_openai_api_key"
      }
    }
  }
}
```

Or use a `.env` file by setting the working directory:

```json
{
  "mcpServers": {
    "peyote-code-context": {
      "command": "python",
      "args": ["/Users/devabhi/Projects/Peyote/Server/src/mcp_server.py"],
      "cwd": "/Users/devabhi/Projects/Peyote/Server"
    }
  }
}
```

4. Restart Cursor to load the MCP server

### Integrating with GitHub Copilot (VS Code)

1. Install the latest version of VS Code with GitHub Copilot extension
2. Configure the MCP server in your VS Code settings (`.vscode/settings.json` or user settings):

```json
{
  "github.copilot.mcp.servers": {
    "peyote-code-context": {
      "command": "python",
      "args": ["/Users/devabhi/Projects/Peyote/Server/src/mcp_server.py"],
      "env": {
        "SUPABASE_URL": "your_supabase_url",
        "SUPABASE_SERVICE_KEY": "your_supabase_service_key",
        "OPENAI_API_KEY": "your_openai_api_key"
      }
    }
  }
}
```

Or use a `.env` file and reference it:

```json
{
  "github.copilot.mcp.servers": {
    "peyote-code-context": {
      "command": "python",
      "args": ["/Users/devabhi/Projects/Peyote/Server/src/mcp_server.py"],
      "cwd": "/Users/devabhi/Projects/Peyote/Server"
    }
  }
}
```

3. Restart VS Code to load the MCP server

### Using in Cursor Chat

Once configured, you can use the tools in Cursor's AI chat:

```
Use @peyote-code-context to get code context for: "def calculate_similarity(a, b):"
```

Or invoke the tools directly through the MCP interface.

### Using in GitHub Copilot Chat

Once configured in VS Code, you can use the tools in Copilot Chat:

```
@peyote-code-context get_code_context with code_snippet: "def calculate_similarity(a, b):"
```

Or:

```
@peyote-code-context augment_prompt with code_snippet: "class UserRepository:"
```

## Available Tools

### get_code_context

Retrieves relevant code context from the codebase based on a code snippet.

**Parameters:**
- `code_snippet` (string, required): The code snippet to find context for

**Example:**
```json
{
  "code_snippet": "def process_payment(amount, user_id):"
}
```

**Returns:** A formatted markdown document with relevant code chunks, including file paths and similarity scores.

### augment_prompt

Augments a code completion prompt with relevant context from the codebase.

**Parameters:**
- `code_snippet` (string, required): The code snippet to augment with context

**Example:**
```json
{
  "code_snippet": "class PaymentProcessor:"
}
```

**Returns:** A complete prompt that can be used with an LLM, including the original code and retrieved context.

## Data Ingestion

Before using the MCP server, you need to ingest your codebase into the vector database:

```bash
python src/ingest.py
```

This will:
1. Parse your codebase
2. Split it into meaningful chunks
3. Generate embeddings using OpenAI
4. Store the embeddings in Supabase

## Architecture

```
User Code (VS Code)
    ↓
GitHub Copilot
    ↓
MCP Server (mcp_server.py)
    ↓
OpenAI Embeddings API
    ↓
Supabase Vector Database
    ↓
Retrieved Context
    ↓
GitHub Copilot (with context)
```

## Monitoring with Datadog

The ingestion service (`ingest.py`) includes comprehensive Datadog integration for monitoring and observability:

- **Custom Metrics**: Track ingestion performance, error rates, and resource usage
- **Error Tracking**: Automatic exception capture with stack traces
- **Structured Logging**: Centralized logging with correlation to traces

### Quick Start

1. Add your Datadog credentials to `.env`:
```env
DD_API_KEY=your_datadog_api_key
DD_APP_KEY=your_datadog_app_key
DD_SERVICE_NAME=peyote-ingest
DD_ENV=production
```

2. Run the service:
```bash
python src/ingest.py
```

3. View metrics in Datadog dashboard

## Troubleshooting

### Cursor-specific issues
- If MCP server doesn't appear in Cursor, check the configuration file location (`~/.cursor/mcp_settings.json` on macOS/Linux, `%APPDATA%\Cursor\mcp_settings.json` on Windows)
- Restart Cursor completely after making configuration changes
- Check Cursor's developer console (Help > Toggle Developer Tools) for MCP-related errors
- Ensure you're using a recent version of Cursor that supports MCP

### Server not connecting
- Ensure Python path is correct in the configuration
- Check that all environment variables are set
- Verify the virtual environment is activated if using one

### No results returned
- Make sure you've run the ingestion script first
- Verify your Supabase database has the `match_code_chunks` function
- Check OpenAI API key is valid

### Permission errors
- Ensure the Python script has execute permissions
- Verify the paths in your configuration are absolute paths

## References

- [MCP Documentation](https://modelcontextprotocol.io/docs/develop/build-server#python)
- [Cursor MCP Integration](https://docs.cursor.com/context/context-mcp)
- [GitHub Copilot MCP Integration](https://docs.github.com/en/copilot/how-tos/provide-context/use-mcp/extend-copilot-chat-with-mcp?tool=visualstudio)
- [Model Context Protocol](https://modelcontextprotocol.io/)

