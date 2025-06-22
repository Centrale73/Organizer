import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox
from agno.agent import Agent
from agno.models.perplexity import Perplexity
from agno.models.groq import Groq
from agno.models.openai import OpenAIChat
from dotenv import load_dotenv
import os
import re
import threading
import shutil
from pathlib import Path
import json
import datetime

# Safe imports with fallbacks
try:
    from loadstorage import loadsessionstorage, loadpersonalitystorage, loadtaskstorage, loaddocumentstorage
except ImportError:
    # Create fallback functions if loadstorage module has issues
    def loadsessionstorage():
        return None
    def loadpersonalitystorage():
        return None
    def loadtaskstorage():
        return None
    def loaddocumentstorage():
        return None

try:
    from agno.document.reader.pdfreader import PDFReader
except ImportError:
    class PDFReader:
        def read(self, filepath):
            return [type('obj', (object,), {'content': f"Could not read PDF: {filepath}"})]

class DocumentOrganizerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("AI Document Organizer with Chat")
        self.root.geometry("1600x1000")
        
        # Initialize data
        self.documents = []
        self.categories = {}
        self.organization_history = []
        self.selected_font = "Arial"
        self.source_folder = ""
        self.target_folder = ""
        
        # Load environment variables
        load_dotenv()  # Fixed function name
        self.pplx_api_key = os.getenv("PERPLEXITY_API_KEY")
        self.groq_api_key = os.getenv("GROQ_API_KEY")
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        
        self.setup_ui()
        self.setup_agents()
    
    def setup_ui(self):
        # Main frame
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Create sidebar frame
        sidebar_frame = ttk.Frame(main_frame, width=350)
        sidebar_frame.pack(side='left', fill='y', padx=(0, 10))
        sidebar_frame.pack_propagate(False)
        
        # Create main content frame
        content_frame = ttk.Frame(main_frame)
        content_frame.pack(side='right', fill='both', expand=True)
        
        self.setup_sidebar(sidebar_frame)
        self.setup_content_area(content_frame)
    
    def setup_sidebar(self, parent):
        # API Configuration
        api_frame = ttk.LabelFrame(parent, text="API Configuration")
        api_frame.pack(fill='x', pady=(0, 10))
        
        ttk.Label(api_frame, text="Choose API Provider:").pack(anchor='w', padx=5, pady=2)
        self.provider_var = tk.StringVar()
        provider_combo = ttk.Combobox(api_frame, textvariable=self.provider_var)
        
        available_providers = []
        if self.pplx_api_key:
            available_providers.append("Perplexity")
        if self.groq_api_key:
            available_providers.append("Groq")
        if self.openai_api_key:
            available_providers.append("OpenAI")
        if not available_providers:
            available_providers = ["Perplexity", "Groq", "OpenAI"]
        
        provider_combo['values'] = available_providers
        provider_combo.pack(fill='x', padx=5, pady=2)
        provider_combo.bind('<<ComboboxSelected>>', self.on_provider_change)
        
        ttk.Label(api_frame, text="Select Model:").pack(anchor='w', padx=5, pady=2)
        self.model_var = tk.StringVar()
        self.model_combo = ttk.Combobox(api_frame, textvariable=self.model_var)
        self.model_combo.pack(fill='x', padx=5, pady=2)
        
        ttk.Label(api_frame, text="API Key (if not in .env):").pack(anchor='w', padx=5, pady=2)
        self.api_key_entry = ttk.Entry(api_frame, show="*")
        self.api_key_entry.pack(fill='x', padx=5, pady=2)
        
        # Folder Selection
        folder_frame = ttk.LabelFrame(parent, text="Folder Configuration")
        folder_frame.pack(fill='x', pady=(0, 10))
        
        ttk.Label(folder_frame, text="Source Folder (PDFs):").pack(anchor='w', padx=5, pady=2)
        source_frame = ttk.Frame(folder_frame)
        source_frame.pack(fill='x', padx=5, pady=2)
        self.source_folder_var = tk.StringVar()
        ttk.Entry(source_frame, textvariable=self.source_folder_var, state='readonly').pack(
            side='left', fill='both', expand=True, padx=(0, 5)
        )
        ttk.Button(source_frame, text="Browse", command=self.select_source_folder).pack(side='right')
        
        ttk.Label(folder_frame, text="Target Folder (Organized):").pack(anchor='w', padx=5, pady=2)
        target_frame = ttk.Frame(folder_frame)
        target_frame.pack(fill='x', padx=5, pady=2)
        self.target_folder_var = tk.StringVar()
        ttk.Entry(target_frame, textvariable=self.target_folder_var, state='readonly').pack(
            side='left', fill='both', expand=True, padx=(0, 5)
        )
        ttk.Button(target_frame, text="Browse", command=self.select_target_folder).pack(side='right')
        
        # Document Processing
        process_frame = ttk.LabelFrame(parent, text="Document Processing")
        process_frame.pack(fill='x', pady=(0, 10))
        
        ttk.Button(process_frame, text="Scan Documents", command=self.scan_documents).pack(
            fill='x', padx=5, pady=2
        )
        ttk.Button(process_frame, text="Categorize Documents", command=self.categorize_documents).pack(
            fill='x', padx=5, pady=2
        )
        ttk.Button(process_frame, text="Organize Documents", command=self.organize_documents).pack(
            fill='x', padx=5, pady=2
        )
        
        self.process_status = ttk.Label(process_frame, text="Ready to process documents")
        self.process_status.pack(anchor='w', padx=5, pady=2)
        
        # Detected Categories
        categories_frame = ttk.LabelFrame(parent, text="Detected Categories")
        categories_frame.pack(fill='both', expand=True, pady=(0, 10))
        
        self.categories_tree = ttk.Treeview(
            categories_frame, columns=('count',), show='tree headings'
        )
        self.categories_tree.heading('#0', text='Category')
        self.categories_tree.heading('count', text='Files')
        self.categories_tree.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Options
        options_frame = ttk.LabelFrame(parent, text="Options")
        options_frame.pack(fill='x')
        
        self.create_subfolder_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            options_frame, text="Create subfolders for categories", 
            variable=self.create_subfolder_var
        ).pack(anchor='w', padx=5, pady=2)
        
        self.preserve_original_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            options_frame, text="Keep original files", 
            variable=self.preserve_original_var
        ).pack(anchor='w', padx=5, pady=2)
    
    def setup_content_area(self, parent):
        notebook = ttk.Notebook(parent)
        notebook.pack(fill='both', expand=True)
        
        # Documents tab
        docs_frame = ttk.Frame(notebook)
        notebook.add(docs_frame, text="Documents")
        
        docs_list_frame = ttk.Frame(docs_frame)
        docs_list_frame.pack(fill='both', expand=True, pady=(0, 10))
        
        columns = ('filename', 'category', 'confidence', 'status')
        self.docs_tree = ttk.Treeview(docs_list_frame, columns=columns, show='headings')
        self.docs_tree.heading('filename', text='File Name')
        self.docs_tree.heading('category', text='Category')
        self.docs_tree.heading('confidence', text='Confidence')
        self.docs_tree.heading('status', text='Status')
        self.docs_tree.column('filename', width=300)
        self.docs_tree.column('category', width=150)
        self.docs_tree.column('confidence', width=100)
        self.docs_tree.column('status', width=100)
        
        scrollbar_docs = ttk.Scrollbar(docs_list_frame, orient='vertical', command=self.docs_tree.yview)
        self.docs_tree.configure(yscrollcommand=scrollbar_docs.set)
        self.docs_tree.pack(side='left', fill='both', expand=True)
        scrollbar_docs.pack(side='right', fill='y')
        
        # Chat tab
        chat_frame = ttk.Frame(notebook)
        notebook.add(chat_frame, text="Document Chat")
        
        # Chat interface layout
        chat_container = ttk.Frame(chat_frame)
        chat_container.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Chat history display
        self.chat_history = scrolledtext.ScrolledText(
            chat_container, 
            wrap=tk.WORD, 
            height=25, 
            state=tk.DISABLED,
            font=(self.selected_font, 10)
        )
        self.chat_history.pack(fill='both', expand=True, pady=(0, 10))
        
        # Configure chat text styles
        self.chat_history.tag_config("user", foreground="#1f77b4")
        self.chat_history.tag_config("assistant", foreground="#2ca02c")
        self.chat_history.tag_config("system", foreground="#ff7f0e")
        
        # Chat input frame
        input_frame = ttk.Frame(chat_container)
        input_frame.pack(fill='x', pady=(0, 5))
        
        # Chat input field
        self.chat_entry = ttk.Entry(input_frame, font=(self.selected_font, 10))
        self.chat_entry.pack(side='left', fill='x', expand=True, padx=(0, 5))
        self.chat_entry.bind('<Return>', self.send_chat_message)
        
        # Send button
        ttk.Button(
            input_frame, 
            text="Send", 
            command=self.send_chat_message
        ).pack(side='right')
        
        # Chat controls
        controls_frame = ttk.Frame(chat_container)
        controls_frame.pack(fill='x')
        
        ttk.Button(
            controls_frame, 
            text="Clear Chat", 
            command=self.clear_chat
        ).pack(side='left')
        
        ttk.Button(
            controls_frame, 
            text="Export Chat", 
            command=self.export_chat
        ).pack(side='left', padx=(5, 0))
        
        # Processing Log tab
        log_frame = ttk.Frame(notebook)
        notebook.add(log_frame, text="Processing Log")
        
        self.log_display = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, state=tk.DISABLED)
        self.log_display.pack(fill='both', expand=True)
        
        # Add welcome message to chat
        self.add_chat_message(
            "Assistant", 
            "Welcome to the Document Chat! I can help you with questions about your documents, categories, and organization. Start by scanning some documents and then ask me anything about them!", 
            "assistant"
        )
    
    def setup_agents(self):
        self.document_analyzer = None
        self.file_organizer = None
        self.category_manager = None
        self.document_chat_agent = None
    
    def on_provider_change(self, event=None):
        provider = self.provider_var.get()
        if provider == "Perplexity":
            self.model_combo['values'] = ("sonar", "sonar-pro")
        elif provider == "Groq":
            self.model_combo['values'] = ("llama-3.3-70b-versatile", "llama3-8b-8192", "mixtral-8x7b-32768")
        elif provider == "OpenAI":
            self.model_combo['values'] = ("gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo")
        
        if self.model_combo['values']:
            self.model_combo.current(0)
    
    def select_source_folder(self):
        folder = filedialog.askdirectory(title="Select Source Folder with PDFs")
        if folder:
            self.source_folder = folder
            self.source_folder_var.set(folder)
    
    def select_target_folder(self):
        folder = filedialog.askdirectory(title="Select Target Folder for Organization")
        if folder:
            self.target_folder = folder
            self.target_folder_var.set(folder)
    
    def create_model_instance(self, provider, model_name, api_key):
        try:
            if provider == "Perplexity":
                return Perplexity(id=model_name, api_key=api_key)
            elif provider == "Groq":
                return Groq(id=model_name, api_key=api_key)
            elif provider == "OpenAI":
                return OpenAIChat(id=model_name, api_key=api_key)
        except Exception as e:
            self.log_message(f"Error creating model instance: {str(e)}")
            return None
    
    def get_current_api_key(self):
        provider = self.provider_var.get()
        if provider == "Perplexity":
            return self.pplx_api_key or self.api_key_entry.get()
        elif provider == "Groq":
            return self.groq_api_key or self.api_key_entry.get()
        elif provider == "OpenAI":
            return self.openai_api_key or self.api_key_entry.get()
        return None
    
    def create_agents(self):
        provider = self.provider_var.get()
        model = self.model_var.get()
        api_key = self.get_current_api_key()
        
        if not all([provider, model, api_key]):
            self.log_message("Error: Missing provider, model, or API key configuration")
            return False
        
        try:
            model_instance = self.create_model_instance(provider, model, api_key)
            if not model_instance:
                return False
            
            # Document Analyzer Agent with improved instructions
            self.document_analyzer = Agent(
                name="Document Analyzer",
                role="Analyze PDF content and categorize documents with high accuracy",
                model=model_instance,
                storage=loaddocumentstorage(),
                instructions="""
                You are an expert document categorization system. Analyze the document content and categorize it precisely.

                CATEGORIES:
                - Financial: invoices, receipts, tax documents, bank statements, financial reports
                - Legal: contracts, agreements, legal notices, court documents
                - Medical: health records, prescriptions, insurance claims, medical reports
                - Academic: research papers, studies, educational materials, theses
                - Business: reports, presentations, memos, business correspondence
                - Personal: letters, certificates, personal documents, identification
                - Technical: manuals, specifications, documentation, guides

                ANALYSIS REQUIREMENTS:
                1. Read the entire document content carefully
                2. Identify key indicators (headers, content themes, document structure)
                3. Assign confidence based on clarity of indicators
                4. Provide specific reasoning

                CONFIDENCE SCORING:
                - 90-100: Very clear indicators, obvious category
                - 70-89: Strong indicators, likely category
                - 50-69: Some indicators, probable category
                - 30-49: Weak indicators, uncertain category
                - 0-29: No clear indicators, default category

                RESPOND ONLY WITH VALID JSON:
                {"category": "CategoryName", "confidence": 85, "reason": "Specific reason based on document content", "subcategory": "OptionalSubcategory"}
                """,
                markdown=False,
                stream=False,
            )
            
            # Document Chat Agent
            self.document_chat_agent = Agent(
                name="Document Chat Assistant",
                role="Answer questions about organized documents and help users find information",
                model=self.create_model_instance(provider, model, api_key),
                storage=loadsessionstorage(),
                instructions="""
                You are a helpful assistant for document organization and management.
                Help users understand their document organization, find specific files, and manage their document workflow.
                Be conversational and provide actionable insights about their document collection.
                """,
                markdown=True,
                stream=False
            )
            
            self.log_message("Agents created successfully")
            return True
            
        except Exception as e:
            error_msg = f"Failed to create agents: {str(e)}"
            self.log_message(error_msg)
            messagebox.showerror("Error", error_msg)
            return False
    
    def log_message(self, message):
        self.log_display.config(state=tk.NORMAL)
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        self.log_display.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_display.config(state=tk.DISABLED)
        self.log_display.see(tk.END)
        self.root.update()
    
    def scan_documents(self):
        if not self.source_folder:
            messagebox.showerror("Error", "Please select a source folder first.")
            return
        
        self.log_message("Starting document scan...")
        self.process_status.config(text="Scanning documents...")
        
        # Clear previous results
        self.documents.clear()
        for item in self.docs_tree.get_children():
            self.docs_tree.delete(item)
        
        try:
            pdf_files = list(Path(self.source_folder).glob("*.pdf"))
            self.log_message(f"Found {len(pdf_files)} PDF files")
            
            reader = PDFReader()
            for pdf_file in pdf_files:
                try:
                    documents = reader.read(str(pdf_file))
                    content = " ".join([doc.content for doc in documents if doc.content])
                    
                    if content.strip():
                        doc_info = {
                            'filename': pdf_file.name,
                            'filepath': str(pdf_file),
                            'content': content[:3000],  # Increased content for better analysis
                            'full_content': content,
                            'category': 'Uncategorized',
                            'confidence': 0,
                            'status': 'Scanned',
                            'reason': '',
                            'subcategory': '',
                            'word_count': len(content.split()),
                            'scan_time': datetime.datetime.now().isoformat()
                        }
                        self.documents.append(doc_info)
                        
                        # Add to tree view
                        self.docs_tree.insert('', tk.END, values=(
                            doc_info['filename'], 
                            doc_info['category'], 
                            f"{doc_info['confidence']}%", 
                            doc_info['status']
                        ))
                        
                        self.log_message(f"Scanned: {pdf_file.name} ({doc_info['word_count']} words)")
                    else:
                        self.log_message(f"Warning: No content extracted from {pdf_file.name}")
                        
                except Exception as e:
                    self.log_message(f"Error scanning {pdf_file.name}: {str(e)}")
            
            self.process_status.config(text=f"Scanned {len(self.documents)} documents")
            self.log_message("Document scan completed")
            
        except Exception as e:
            self.log_message(f"Error during scanning: {str(e)}")
            self.process_status.config(text="Scan failed")
    
    def categorize_documents(self):
        if not self.documents:
            messagebox.showerror("Error", "Please scan documents first.")
            return
        
        if not self.create_agents():
            return
        
        self.log_message("Starting document categorization...")
        self.process_status.config(text="Categorizing documents...")
        
        # Process documents in a separate thread
        threading.Thread(target=self.categorize_documents_thread, daemon=True).start()
    
    def categorize_documents_thread(self):
        try:
            for i, doc in enumerate(self.documents):
                self.root.after(0, lambda d=doc: self.log_message(f"Categorizing {d['filename']}..."))
                
                try:
                    if not self.document_analyzer:
                        self.root.after(0, lambda: self.log_message("Document analyzer not available"))
                        continue
                    
                    # Enhanced prompt with document content
                    prompt = f"""
                    Document: {doc['filename']}
                    Content: {doc['content']}
                    
                    Analyze this document and provide categorization with high confidence.
                    """
                    
                    response = self.document_analyzer.run(prompt)
                    content = response.content if hasattr(response, 'content') else str(response)
                    
                    # More robust JSON parsing
                    try:
                        # Clean the response and extract JSON
                        cleaned_content = content.strip()
                        
                        # Try to find JSON in the response
                        json_start = cleaned_content.find('{')
                        json_end = cleaned_content.rfind('}') + 1
                        
                        if json_start != -1 and json_end > json_start:
                            json_str = cleaned_content[json_start:json_end]
                            result = json.loads(json_str)
                            
                            # Extract and validate results
                            doc['category'] = result.get('category', 'General').strip()
                            doc['confidence'] = max(0, min(100, int(result.get('confidence', 50))))
                            doc['reason'] = result.get('reason', 'Automated categorization').strip()
                            doc['subcategory'] = result.get('subcategory', '').strip()
                            doc['status'] = 'Categorized'
                            
                        else:
                            # Fallback parsing if JSON not found
                            doc['category'] = 'General'
                            doc['confidence'] = 30
                            doc['reason'] = 'Unable to parse AI response'
                            doc['status'] = 'Partial'
                            
                    except json.JSONDecodeError as je:
                        self.root.after(0, lambda e=str(je): self.log_message(f"JSON parsing error: {e}"))
                        doc['category'] = 'General'
                        doc['confidence'] = 25
                        doc['reason'] = 'JSON parsing failed'
                        doc['status'] = 'Failed'
                    
                    # Update tree view with consistent formatting
                    def update_tree():
                        for item in self.docs_tree.get_children():
                            if self.docs_tree.item(item)['values'][0] == doc['filename']:
                                self.docs_tree.item(item, values=(
                                    doc['filename'], 
                                    doc['category'], 
                                    f"{doc['confidence']}%", 
                                    doc['status']
                                ))
                                break
                    
                    self.root.after(0, update_tree)
                    self.root.after(0, lambda d=doc: self.log_message(
                        f"Categorized {d['filename']}: {d['category']} ({d['confidence']}% confidence)"
                    ))
                    
                except Exception as e:
                    error_msg = f"Error categorizing {doc['filename']}: {str(e)}"
                    self.root.after(0, lambda msg=error_msg: self.log_message(msg))
                    doc['status'] = 'Error'
                    doc['category'] = 'Error'
                    doc['confidence'] = 0
            
            self.root.after(0, self.update_categories_display)
            self.root.after(0, lambda: self.process_status.config(text="Categorization completed"))
            self.root.after(0, lambda: self.log_message("Document categorization completed"))
            
        except Exception as e:
            self.root.after(0, lambda err=str(e): self.log_message(f"Categorization error: {err}"))
    
    def update_categories_display(self):
        # Clear categories tree
        for item in self.categories_tree.get_children():
            self.categories_tree.delete(item)
        
        # Count documents by category
        category_counts = {}
        for doc in self.documents:
            category = doc.get('category', 'Uncategorized')
            if category not in category_counts:
                category_counts[category] = 0
            category_counts[category] += 1
        
        # Populate categories tree
        for category, count in sorted(category_counts.items()):
            self.categories_tree.insert('', tk.END, text=category, values=(count,))
    
    def organize_documents(self):
        if not self.target_folder:
            messagebox.showerror("Error", "Please select a target folder first.")
            return
        
        # Check if documents are categorized
        categorized_docs = [doc for doc in self.documents 
                          if doc.get('category') not in ['Uncategorized', 'Error', None]]
        
        if not categorized_docs:
            messagebox.showerror("Error", "No documents have been successfully categorized. Please categorize documents first.")
            return
        
        self.log_message(f"Starting organization of {len(categorized_docs)} categorized documents...")
        self.process_status.config(text="Organizing documents...")
        
        try:
            target_path = Path(self.target_folder)
            organized_count = 0
            failed_count = 0
            
            for doc in categorized_docs:
                try:
                    category = doc.get('category', 'General')
                    if not category or category in ['Uncategorized', 'Error']:
                        continue
                    
                    # Create category folder
                    category_folder = target_path / category
                    category_folder.mkdir(parents=True, exist_ok=True)
                    
                    # Create subcategory folder if specified
                    if doc.get('subcategory') and doc['subcategory'].strip():
                        final_folder = category_folder / doc['subcategory'].strip()
                        final_folder.mkdir(parents=True, exist_ok=True)
                    else:
                        final_folder = category_folder
                    
                    # Handle source file
                    source_file = Path(doc['filepath'])
                    if not source_file.exists():
                        self.log_message(f"Warning: Source file not found: {source_file}")
                        doc['status'] = 'Source Missing'
                        failed_count += 1
                        continue
                    
                    # Determine target file path
                    target_file = final_folder / source_file.name
                    
                    # Handle duplicate names
                    counter = 1
                    original_target = target_file
                    while target_file.exists():
                        stem = original_target.stem
                        suffix = original_target.suffix
                        target_file = final_folder / f"{stem}_{counter}{suffix}"
                        counter += 1
                    
                    # Copy or move file
                    if self.preserve_original_var.get():
                        shutil.copy2(source_file, target_file)
                        action = "Copied"
                    else:
                        shutil.move(str(source_file), str(target_file))
                        action = "Moved"
                    
                    doc['status'] = action
                    doc['organized_path'] = str(target_file)
                    organized_count += 1
                    
                    self.log_message(f"{action}: {doc['filename']} -> {category}/{doc.get('subcategory', '')}")
                    
                except Exception as file_error:
                    error_msg = f"Failed to organize {doc['filename']}: {str(file_error)}"
                    self.log_message(error_msg)
                    doc['status'] = 'Failed'
                    failed_count += 1
            
            # Update tree view for all documents
            for item in self.docs_tree.get_children():
                item_values = self.docs_tree.item(item)['values']
                filename = item_values[0]
                
                # Find corresponding document
                doc = next((d for d in self.documents if d['filename'] == filename), None)
                if doc:
                    self.docs_tree.item(item, values=(
                        doc['filename'], 
                        doc.get('category', 'Unknown'), 
                        f"{doc.get('confidence', 0)}%", 
                        doc.get('status', 'Unknown')
                    ))
            
            # Final status update
            if organized_count > 0:
                self.process_status.config(text=f"Organization completed: {organized_count} files organized")
                self.log_message(f"✅ Organization completed successfully!")
                self.log_message(f"   - Organized: {organized_count} files")
                if failed_count > 0:
                    self.log_message(f"   - Failed: {failed_count} files")
            else:
                self.process_status.config(text="Organization failed - no files processed")
                self.log_message("❌ No files were organized. Check categorization results.")
            
        except Exception as e:
            error_msg = f"Organization error: {str(e)}"
            self.log_message(error_msg)
            self.process_status.config(text="Organization failed")
            messagebox.showerror("Organization Error", error_msg)
    
    # Chat functionality methods
    def send_chat_message(self, event=None):
        """Send a chat message and get AI response"""
        message = self.chat_entry.get().strip()
        if not message:
            return
        
        # Clear input
        self.chat_entry.delete(0, tk.END)
        
        # Display user message
        self.add_chat_message("You", message, "user")
        
        # Process in background thread
        threading.Thread(
            target=self.process_chat_message, 
            args=(message,), 
            daemon=True
        ).start()

    def process_chat_message(self, message):
        """Process chat message with AI agent"""
        try:
            # Create agents if not already created
            if not self.document_chat_agent:
                if not self.create_agents():
                    error_msg = "Please configure API settings first."
                    self.root.after(0, lambda: self.add_chat_message("System", error_msg, "system"))
                    return
            
            # Prepare context about documents
            context = self.prepare_document_context()
            
            # Create enhanced prompt with document context
            enhanced_message = f"""
            Context about current documents:
            {context}
            
            User question: {message}
            """
            
            # Get AI response
            response = self.document_chat_agent.run(enhanced_message)
            content = response.content if hasattr(response, 'content') else str(response)
            
            # Display AI response
            self.root.after(0, lambda: self.add_chat_message("Assistant", content, "assistant"))
            
        except Exception as e:
            error_msg = f"Error processing message: {str(e)}"
            self.root.after(0, lambda: self.add_chat_message("System", error_msg, "system"))

    def prepare_document_context(self):
        """Prepare context about current documents for the chat agent"""
        if not self.documents:
            return "No documents have been processed yet."
        
        context_parts = [
            f"Total documents: {len(self.documents)}",
            "\nDocument summary:"
        ]
        
        # Group documents by category
        categories = {}
        for doc in self.documents:
            category = doc.get('category', 'Uncategorized')
            if category not in categories:
                categories[category] = []
            categories[category].append({
                'filename': doc['filename'],
                'confidence': doc.get('confidence', 0),
                'status': doc.get('status', 'Unknown'),
                'word_count': doc.get('word_count', 0)
            })
        
        for category, files in categories.items():
            context_parts.append(f"\n{category}: {len(files)} files")
            for file in files[:3]:  # Show first 3 files
                context_parts.append(f"  - {file['filename']} (confidence: {file['confidence']}%, status: {file['status']})")
            if len(files) > 3:
                context_parts.append(f"  ... and {len(files) - 3} more")
        
        # Add processing statistics
        total_words = sum(doc.get('word_count', 0) for doc in self.documents)
        categorized = sum(1 for doc in self.documents if doc.get('category', 'Uncategorized') != 'Uncategorized')
        organized = sum(1 for doc in self.documents if doc.get('status', '') in ['Copied', 'Moved'])
        
        context_parts.append(f"\nProcessing stats:")
        context_parts.append(f"- Categorized: {categorized}/{len(self.documents)} documents")
        context_parts.append(f"- Organized: {organized}/{len(self.documents)} documents")
        context_parts.append(f"- Total words processed: {total_words:,}")
        
        return "".join(context_parts)

    def add_chat_message(self, sender, message, message_type):
        """Add a message to the chat history"""
        self.chat_history.config(state=tk.NORMAL)
        
        # Add timestamp
        timestamp = datetime.datetime.now().strftime("%H:%M")
        
        # Style message based on type
        if message_type == "user":
            self.chat_history.insert(tk.END, f"[{timestamp}] {sender}: {message}\n\n", "user")
        elif message_type == "assistant":
            self.chat_history.insert(tk.END, f"[{timestamp}] {sender}:\n{message}\n\n", "assistant")
        elif message_type == "system":
            self.chat_history.insert(tk.END, f"[{timestamp}] {sender}: {message}\n\n", "system")
        
        self.chat_history.config(state=tk.DISABLED)
        self.chat_history.see(tk.END)

    def clear_chat(self):
        """Clear the chat history"""
        self.chat_history.config(state=tk.NORMAL)
        self.chat_history.delete(1.0, tk.END)
        self.chat_history.config(state=tk.DISABLED)
        self.add_chat_message("System", "Chat history cleared.", "system")

    def export_chat(self):
        """Export chat history to a text file"""
        try:
            filename = filedialog.asksaveasfilename(
                title="Export Chat History",
                defaultextension=".txt",
                filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
            )
            
            if filename:
                chat_content = self.chat_history.get(1.0, tk.END)
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(f"Document Organizer Chat Export\n")
                    f.write(f"Exported on: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write("="*50 + "\n\n")
                    f.write(chat_content)
                
                self.add_chat_message("System", f"Chat exported to {filename}", "system")
                
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to export chat: {str(e)}")


if __name__ == "__main__":
    root = tk.Tk()
    app = DocumentOrganizerApp(root)
    root.mainloop()
