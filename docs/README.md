# Perplexity Validator

A serverless system that validates and enriches Excel data using AI, with a focus on conversational configuration and interactive previews.

## Features

-   **Conversational Configuration**: Use natural language to generate and refine validation configurations.
-   **Interactive Previews**: Get a preview of the validation results before processing the entire table.
-   **Multi-mode Processing**: Synchronous preview, asynchronous preview, and full validation modes.
-   **Intelligent Caching**: S3-based caching to reduce API calls and costs.
-   **Comprehensive Tracking**: DynamoDB tracking of all validation sessions.
-   **Email Delivery**: Automatic email delivery of validation results.
-   **API Gateway Interface**: REST API for easy integration.

## Architecture

The backend is built on a serverless architecture using AWS Lambda, API Gateway, and S3. It consists of three main Lambda functions: Interface, Config, and Validation.

For a detailed explanation of the backend architecture, please refer to the [Backend Architecture](backend_architecture.md) document.

```
API Gateway → Interface Lambda → Validation Lambda
                    ↓           ↘
                 WebSocket       Config Lambda
                    ↓
             Frontend (for real-time updates)
```

## Quick Start

### Local Development

Start a local development server:

```bash
# Development mode (uses -dev.html)
./start-local.sh

# Production mode (uses .html)
./start-local.sh prod

# Custom port
./start-local.sh --port 3000
```

### Documentation

- **[QUICK_START.md](QUICK_START.md)** - Setup and usage instructions
- **[SECURITY.md](SECURITY.md)** - Comprehensive security guide (NEW)
- **[INFRASTRUCTURE_GUIDE.md](INFRASTRUCTURE_GUIDE.md)** - System architecture
- **[../DEPLOYMENT_INSTRUCTIONS.md](../DEPLOYMENT_INSTRUCTIONS.md)** - Deployment steps
- **[../SECURITY_FIXES_IMPLEMENTED.md](../SECURITY_FIXES_IMPLEMENTED.md)** - Security audit results



## Project Structure

The project is structured as follows:

```
perplexityValidator/
├── docs/
├── frontend/
├── src/
│   ├── lambdas/
│   │   ├── interface/
│   │   ├── config/
│   │   └── validation/
│   └── shared/
├── tables/
└── tests/
```

## Requirements

-   Python 3.9+
-   AWS Account with appropriate permissions
-   Perplexity AI API key (stored in AWS Parameter Store)

## License

MIT License 