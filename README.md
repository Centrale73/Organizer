# AI Document Organizer

An intelligent desktop application that automates your document management workflow. Built with Python and the [Agno](https://github.com/agno-agi/agno) framework, this tool uses Large Language Models (LLMs) to scan, analyze, and organize PDF files into structured directories automatically.

Designed for business owners and professionals to eliminate administrative overhead.

## 🚀 Features

- **AI-Powered Categorization**: Automatically detects document types (Financial, Legal, Medical, Technical, etc.) using advanced LLMs.
- **Smart Filing**: Moves or copies files into a clean folder structure based on their content (e.g., `Target/Financial/Invoices/file.pdf`).
- **Interactive Document Chat**: Ask questions about your documents (e.g., "What is the total on the Invoice from March?") using the built-in RAG agent.
- **Multi-Provider Support**: Switch seamlessly between **Perplexity** (best for accuracy), **Groq** (fastest speed), and **OpenAI**.
- **Resilient Architecture**: Features background threading to keep the UI responsive during bulk processing and robust SQLite storage for session history.

## 🛠️ Installation

### Prerequisites
- Python 3.10 or higher
- A valid API key from Perplexity, Groq, or OpenAI

### Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/Lmao53and2/Organizer.git
   cd Organizer
