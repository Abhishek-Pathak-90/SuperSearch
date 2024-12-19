import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import threading
from datetime import datetime
import mimetypes
import queue
from concurrent.futures import ThreadPoolExecutor
import time

class FileSearchApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Super Search")
        self.root.geometry("1200x700")
        
        # Configure style for modern look
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("Custom.Horizontal.TProgressbar", 
                       troughcolor='#E0E0E0', 
                       background='#4CAF50')
        
        # Create main frame
        main_frame = ttk.Frame(root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        
        # Search frame
        search_frame = ttk.LabelFrame(main_frame, text="Search Options", padding="5")
        search_frame.grid(row=0, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)
        search_frame.columnconfigure(1, weight=1)
        
        # Search path
        ttk.Label(search_frame, text="Search in:").grid(row=0, column=0, padx=5)
        self.path_var = tk.StringVar(value=os.path.expanduser("~"))
        self.path_entry = ttk.Entry(search_frame, textvariable=self.path_var)
        self.path_entry.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=5)
        ttk.Button(search_frame, text="Browse", command=self.browse_directory).grid(row=0, column=2, padx=5)
        
        # Search query
        ttk.Label(search_frame, text="Search for:").grid(row=1, column=0, padx=5, pady=5)
        self.query_var = tk.StringVar()
        self.query_entry = ttk.Entry(search_frame, textvariable=self.query_var)
        self.query_entry.grid(row=1, column=1, sticky=(tk.W, tk.E), padx=5, pady=5)
        
        # Search options
        options_frame = ttk.Frame(search_frame)
        options_frame.grid(row=2, column=0, columnspan=3, sticky=(tk.W, tk.E))
        
        self.search_contents = tk.BooleanVar(value=False)
        ttk.Checkbutton(options_frame, text="Search file contents", variable=self.search_contents).pack(side=tk.LEFT, padx=5)
        
        self.case_sensitive = tk.BooleanVar(value=False)
        ttk.Checkbutton(options_frame, text="Case sensitive", variable=self.case_sensitive).pack(side=tk.LEFT, padx=5)
        
        # Search button
        self.search_button = ttk.Button(options_frame, text="Search", command=self.start_search, style='Accent.TButton')
        self.search_button.pack(side=tk.RIGHT, padx=5)
        
        # Progress frame
        progress_frame = ttk.Frame(main_frame)
        progress_frame.grid(row=1, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)
        
        # Progress bar
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(
            progress_frame, 
            mode='determinate', 
            variable=self.progress_var,
            style="Custom.Horizontal.TProgressbar"
        )
        self.progress_bar.pack(fill=tk.X, padx=5)
        
        # Status label
        self.status_var = tk.StringVar(value="Ready")
        self.status_label = ttk.Label(progress_frame, textvariable=self.status_var)
        self.status_label.pack(pady=2)
        
        # Results treeview
        columns = ("name", "path", "size", "modified", "type")
        self.tree = ttk.Treeview(main_frame, columns=columns, show="headings", selectmode="extended")
        self.tree.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        main_frame.rowconfigure(2, weight=1)
        
        # Configure treeview columns
        headings = {
            "name": "Name",
            "path": "Path",
            "size": "Size",
            "modified": "Modified",
            "type": "Type"
        }
        
        for col, heading in headings.items():
            self.tree.heading(col, text=heading, command=lambda c=col: self.sort_treeview(c))
            self.tree.column(col, width=0)  # Let pack algorithm decide width
        
        # Adjust column widths
        self.tree.column("name", width=200, minwidth=100)
        self.tree.column("path", width=400, minwidth=200)
        self.tree.column("size", width=100, minwidth=80)
        self.tree.column("modified", width=150, minwidth=100)
        self.tree.column("type", width=150, minwidth=100)
        
        # Scrollbars
        y_scrollbar = ttk.Scrollbar(main_frame, orient=tk.VERTICAL, command=self.tree.yview)
        y_scrollbar.grid(row=2, column=2, sticky=(tk.N, tk.S))
        x_scrollbar = ttk.Scrollbar(main_frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        x_scrollbar.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E))
        
        self.tree.configure(yscrollcommand=y_scrollbar.set, xscrollcommand=x_scrollbar.set)
        
        # Right-click menu
        self.context_menu = tk.Menu(self.root, tearoff=0)
        self.context_menu.add_command(label="Open File", command=self.open_file)
        self.context_menu.add_command(label="Open Containing Folder", command=self.open_folder)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Copy Path", command=self.copy_path)
        
        self.tree.bind("<Button-3>", self.show_context_menu)
        self.tree.bind("<Double-1>", lambda e: self.open_file())
        
        # Initialize search state
        self.result_queue = queue.Queue()
        self.is_searching = False
        self.total_files = 0
        self.processed_files = 0
        self.start_time = 0
        
        # Start queue processing
        self.process_queue()
        
        # Bind Enter key to start search
        self.query_entry.bind('<Return>', lambda e: self.start_search())
        
    def browse_directory(self):
        directory = filedialog.askdirectory(initialdir=self.path_var.get())
        if directory:
            self.path_var.set(directory)
    
    def format_size(self, size):
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"
    
    def get_file_type(self, path):
        mime_type, _ = mimetypes.guess_type(path)
        if mime_type:
            return mime_type.split('/')[-1].upper()
        return os.path.splitext(path)[1][1:].upper() or "Unknown"
    
    def count_files(self, path):
        count = 0
        try:
            for root, _, files in os.walk(path):
                if not self.is_searching:
                    break
                count += len(files)
                if count % 1000 == 0:
                    self.status_var.set(f"Scanning directory... Found {count:,} files")
                    self.root.update_idletasks()
        except Exception:
            pass
        return count
    
    def search_files(self):
        try:
            root_path = self.path_var.get()
            query = self.query_var.get()
            search_contents = self.search_contents.get()
            case_sensitive = self.case_sensitive.get()
            
            if not case_sensitive:
                query = query.lower()
            
            # Count total files first
            self.status_var.set("Scanning directory...")
            self.total_files = self.count_files(root_path)
            self.processed_files = 0
            self.start_time = time.time()
            
            def process_file(args):
                if not self.is_searching:
                    return None
                    
                root, file = args
                file_path = os.path.join(root, file)
                try:
                    # Update progress
                    self.processed_files += 1
                    if self.processed_files % 100 == 0:
                        progress = (self.processed_files / self.total_files) * 100
                        self.progress_var.set(progress)
                        elapsed = time.time() - self.start_time
                        speed = self.processed_files / elapsed if elapsed > 0 else 0
                        self.status_var.set(
                            f"Processed: {self.processed_files:,}/{self.total_files:,} files "
                            f"({progress:.1f}%) - {speed:.0f} files/sec"
                        )
                    
                    # Check filename match
                    filename = file if case_sensitive else file.lower()
                    if query in filename:
                        return self.get_file_info(file_path)
                        
                    # Check content match if needed
                    if search_contents and os.path.getsize(file_path) < 1000000:  # 1MB limit
                        try:
                            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                                content = f.read() if case_sensitive else f.read().lower()
                                if query in content:
                                    return self.get_file_info(file_path)
                        except (PermissionError, OSError):
                            pass
                            
                except Exception:
                    pass
                return None
            
            # Use ThreadPoolExecutor for parallel processing
            with ThreadPoolExecutor(max_workers=os.cpu_count()) as executor:
                file_list = ((root, file) for root, _, files in os.walk(root_path) for file in files)
                for result in executor.map(process_file, file_list):
                    if result:
                        self.result_queue.put(result)
                    
                    if not self.is_searching:
                        break
            
            if self.is_searching:
                elapsed = time.time() - self.start_time
                self.status_var.set(
                    f"Search complete - Processed {self.processed_files:,} files in {elapsed:.1f} seconds"
                )
        except Exception as e:
            self.status_var.set(f"Error: {str(e)}")
        finally:
            self.is_searching = False
            self.progress_var.set(100)
            self.search_button.configure(text="Search")
    
    def get_file_info(self, file_path):
        try:
            stats = os.stat(file_path)
            return {
                "name": os.path.basename(file_path),
                "path": file_path,
                "size": self.format_size(stats.st_size),
                "modified": datetime.fromtimestamp(stats.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
                "type": self.get_file_type(file_path)
            }
        except (PermissionError, OSError):
            return None
    
    def process_queue(self):
        try:
            while True:
                result = self.result_queue.get_nowait()
                if result:
                    self.tree.insert("", "end", values=(
                        result["name"],
                        result["path"],
                        result["size"],
                        result["modified"],
                        result["type"]
                    ))
        except queue.Empty:
            pass
        finally:
            self.root.after(100, self.process_queue)
    
    def sort_treeview(self, col):
        items = [(self.tree.set(item, col), item) for item in self.tree.get_children('')]
        items.sort()
        for index, (_, item) in enumerate(items):
            self.tree.move(item, '', index)
    
    def start_search(self):
        if self.is_searching:
            self.is_searching = False
            self.search_button.configure(text="Search")
            self.status_var.set("Search stopped")
            return
            
        if not self.query_var.get():
            messagebox.showwarning("Warning", "Please enter a search term")
            return
            
        if not os.path.exists(self.path_var.get()):
            messagebox.showwarning("Warning", "Please select a valid directory")
            return
        
        self.tree.delete(*self.tree.get_children())
        self.is_searching = True
        self.search_button.configure(text="Stop")
        self.progress_var.set(0)
        self.status_var.set("Starting search...")
        
        threading.Thread(target=self.search_files, daemon=True).start()
    
    def show_context_menu(self, event):
        item = self.tree.identify_row(event.y)
        if item:
            self.tree.selection_set(item)
            self.context_menu.tk_popup(event.x_root, event.y_root)
    
    def open_file(self):
        selection = self.tree.selection()
        if selection:
            file_path = self.tree.item(selection[0])['values'][1]
            os.startfile(file_path)
    
    def open_folder(self):
        selection = self.tree.selection()
        if selection:
            file_path = self.tree.item(selection[0])['values'][1]
            folder_path = os.path.dirname(file_path)
            os.startfile(folder_path)
    
    def copy_path(self):
        selection = self.tree.selection()
        if selection:
            file_path = self.tree.item(selection[0])['values'][1]
            self.root.clipboard_clear()
            self.root.clipboard_append(file_path)

if __name__ == '__main__':
    root = tk.Tk()
    app = FileSearchApp(root)
    root.mainloop()
