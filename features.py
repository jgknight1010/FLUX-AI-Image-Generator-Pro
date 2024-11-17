import customtkinter as ctk
import tkinter as tk
from tkinter import ttk, filedialog
from PIL import Image, ImageTk
import os
import json

class ImagePreview:
    def __init__(self, parent_frame):
        self.parent = parent_frame
        self.zoom_level = 1.0
        self.setup_preview_area()
    
    def setup_preview_area(self):
        # Preview frame with controls
        self.preview_frame = ctk.CTkFrame(self.parent)
        self.preview_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Control buttons
        self.controls_frame = ctk.CTkFrame(self.preview_frame)
        self.controls_frame.pack(fill=tk.X)
        
        ctk.CTkButton(self.controls_frame, text="Zoom In", 
                     command=self.zoom_in).pack(side=tk.LEFT, padx=2)
        ctk.CTkButton(self.controls_frame, text="Zoom Out", 
                     command=self.zoom_out).pack(side=tk.LEFT, padx=2)
        ctk.CTkButton(self.controls_frame, text="Reset", 
                     command=self.reset_zoom).pack(side=tk.LEFT, padx=2)
        ctk.CTkButton(self.controls_frame, text="Save", 
                     command=self.save_image).pack(side=tk.LEFT, padx=2)
        
        # Canvas for image display
        self.canvas = tk.Canvas(self.preview_frame, bg='#2b2b2b',
                              highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        # Scrollbars
        self.scrolly = ttk.Scrollbar(self.preview_frame, orient=tk.VERTICAL,
                                   command=self.canvas.yview)
        self.scrolly.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.scrollx = ttk.Scrollbar(self.preview_frame, orient=tk.HORIZONTAL,
                                   command=self.canvas.xview)
        self.scrollx.pack(side=tk.BOTTOM, fill=tk.X)
        
        self.canvas.configure(xscrollcommand=self.scrollx.set,
                            yscrollcommand=self.scrolly.set)
        
        # Bind mouse events
        self.canvas.bind("<ButtonPress-1>", self.start_pan)
        self.canvas.bind("<B1-Motion>", self.pan)
        self.canvas.bind("<MouseWheel>", self.mouse_wheel)
        
        self.current_image = None
        self.image_on_canvas = None

    def update_image(self, image_path):
        try:
            image = Image.open(image_path)
            self.current_image = image
            self.display_image()
        except Exception as e:
            print(f"Error loading image: {e}")

    def display_image(self):
        if self.current_image:
            # Calculate new size
            new_width = int(self.current_image.width * self.zoom_level)
            new_height = int(self.current_image.height * self.zoom_level)
            
            # Resize image
            resized = self.current_image.resize((new_width, new_height),
                                              Image.Resampling.LANCZOS)
            
            # Convert to PhotoImage
            self.photo = ImageTk.PhotoImage(resized)
            
            # Update canvas
            if self.image_on_canvas:
                self.canvas.delete(self.image_on_canvas)
            
            self.image_on_canvas = self.canvas.create_image(
                0, 0, anchor="nw", image=self.photo
            )
            
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def zoom_in(self):
        self.zoom_level *= 1.2
        self.display_image()

    def zoom_out(self):
        self.zoom_level *= 0.8
        self.display_image()

    def reset_zoom(self):
        self.zoom_level = 1.0
        self.display_image()

    def start_pan(self, event):
        self.canvas.scan_mark(event.x, event.y)

    def pan(self, event):
        self.canvas.scan_dragto(event.x, event.y, gain=1)

    def mouse_wheel(self, event):
        if event.delta > 0:
            self.zoom_in()
        else:
            self.zoom_out()

    def save_image(self):
        if self.current_image:
            file_path = filedialog.asksaveasfilename(
                defaultextension=".png",
                filetypes=[("PNG files", "*.png"),
                          ("JPEG files", "*.jpg"),
                          ("All files", "*.*")]
            )
            if file_path:
                self.current_image.save(file_path)

class GalleryView:
    def __init__(self, parent_frame):
        self.parent = parent_frame
        self.setup_gallery()
        
    def setup_gallery(self):
        # Search and filter frame
        control_frame = ctk.CTkFrame(self.parent)
        control_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Search
        self.search_var = tk.StringVar()
        search_entry = ctk.CTkEntry(control_frame, 
                                  placeholder_text="Search...",
                                  textvariable=self.search_var)
        search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        # Filter dropdown
        self.filter_var = tk.StringVar(value="All")
        filter_menu = ctk.CTkOptionMenu(control_frame,
                                      variable=self.filter_var,
                                      values=["All", "Recent", "Favorites"])
        filter_menu.pack(side=tk.RIGHT, padx=5)
        
        # Gallery grid frame
        self.gallery_frame = ctk.CTkScrollableFrame(self.parent)
        self.gallery_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Grid layout
        self.grid_size = 4
        self.current_row = 0
        self.current_col = 0

    def add_image(self, image_path, metadata=None):
        try:
            # Load and resize image for thumbnail
            image = Image.open(image_path)
            image.thumbnail((150, 150))
            photo = ImageTk.PhotoImage(image)
            
            # Create frame for image
            frame = ctk.CTkFrame(self.gallery_frame)
            frame.grid(row=self.current_row, column=self.current_col,
                      padx=5, pady=5)
            
            # Image label
            label = tk.Label(frame, image=photo)
            label.image = photo  # Keep reference
            label.pack()
            
            # Update grid position
            self.current_col += 1
            if self.current_col >= self.grid_size:
                self.current_col = 0
                self.current_row += 1
                
        except Exception as e:
            print(f"Error adding image to gallery: {e}")

    def clear_gallery(self):
        for widget in self.gallery_frame.winfo_children():
            widget.destroy()
        self.current_row = 0
        self.current_col = 0

    def load_directory(self, directory):
        self.clear_gallery()
        for filename in os.listdir(directory):
            if filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                self.add_image(os.path.join(directory, filename))

class PromptLibrary:
    def __init__(self, parent_frame):
        self.parent = parent_frame
        self.favorites = self.load_favorites()
        self.setup_library()
        
    def load_favorites(self):
        try:
            with open('favorites.json', 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def save_favorites(self):
        with open('favorites.json', 'w') as f:
            json.dump(self.favorites, f, indent=2)

    def setup_library(self):
        # Create frames
        control_frame = ctk.CTkFrame(self.parent)
        control_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Add prompt button
        ctk.CTkButton(control_frame, text="Add Prompt",
                     command=self.add_prompt).pack(side=tk.LEFT, padx=5)
        
        # Search
        self.search_var = tk.StringVar()
        search_entry = ctk.CTkEntry(control_frame,
                                  placeholder_text="Search prompts...",
                                  textvariable=self.search_var)
        search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        # Prompts list
        self.prompts_frame = ctk.CTkScrollableFrame(self.parent)
        self.prompts_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.update_prompt_list()

    def add_prompt(self):
        # Add new prompt dialog
        dialog = PromptDialog(self.parent)
        self.parent.wait_window(dialog)
        
        if dialog.prompt:
            self.favorites.append({
                "prompt": dialog.prompt,
                "tags": dialog.tags
            })
            self.save_favorites()
            self.update_prompt_list()

    def update_prompt_list(self):
        # Clear current list
        for widget in self.prompts_frame.winfo_children():
            widget.destroy()
        
        # Add prompts
        for prompt in self.favorites:
            self.create_prompt_widget(prompt)

    def create_prompt_widget(self, prompt_data):
        frame = ctk.CTkFrame(self.prompts_frame)
        frame.pack(fill=tk.X, padx=5, pady=2)
        
        ctk.CTkLabel(frame, text=prompt_data["prompt"]).pack(
            side=tk.LEFT, padx=5)
        
        ctk.CTkButton(frame, text="Use",
                     command=lambda: self.use_prompt(prompt_data["prompt"])).pack(
            side=tk.RIGHT, padx=5)

    def use_prompt(self, prompt):
        # This method should be connected to the main application
        pass

class PromptDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Add Prompt")
        self.prompt = None
        self.tags = []
        self.setup_dialog()
        
    def setup_dialog(self):
        # Prompt entry
        prompt_frame = ctk.CTkFrame(self)
        prompt_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ctk.CTkLabel(prompt_frame, text="Prompt:").pack(anchor=tk.W)
        self.prompt_entry = ctk.CTkTextbox(prompt_frame, height=100)
        self.prompt_entry.pack(fill=tk.X)
        
        # Tags
        tags_frame = ctk.CTkFrame(self)
        tags_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ctk.CTkLabel(tags_frame, text="Tags (comma separated):").pack(anchor=tk.W)
        self.tags_entry = ctk.CTkEntry(tags_frame)
        self.tags_entry.pack(fill=tk.X)
        
        # Buttons
        button_frame = ctk.CTkFrame(self)
        button_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ctk.CTkButton(button_frame, text="Save",
                     command=self.save_prompt).pack(side=tk.LEFT, padx=5)
        ctk.CTkButton(button_frame, text="Cancel",
                     command=self.destroy).pack(side=tk.RIGHT, padx=5)

    def save_prompt(self):
        self.prompt = self.prompt_entry.get("1.0", tk.END).strip()
        self.tags = [tag.strip() for tag in self.tags_entry.get().split(",")
                    if tag.strip()]
        self.destroy()
