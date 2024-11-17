import customtkinter as ctk
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import json
import requests
import os
from PIL import Image, ImageTk
from datetime import datetime
import threading
import queue
import configparser
from pathlib import Path
from dataclasses import dataclass
import logging
import logging.handlers
import traceback
from typing import Optional, List
import time
import sys

# ----------------------------
# Data Classes
# ----------------------------

@dataclass
class GenerationParams:
    prompt: str
    width: int = 1024
    height: int = 768
    safety_tolerance: int = 2
    seed: Optional[int] = None
    guidance: float = 2.5
    steps: int = 40
    prompt_upsampling: bool = False
    raw_mode: bool = False
    aspect_ratio: str = "16:9"
    output_format: str = "jpeg"

    def validate(self):
        """Validate generation parameters"""
        if not self.prompt:
            raise ValueError("Prompt cannot be empty")
        if self.width % 32 != 0 or self.height % 32 != 0:
            raise ValueError("Width and height must be multiples of 32")
        if not 0 <= self.safety_tolerance <= 3:
            raise ValueError("Safety tolerance must be between 0 and 3")
        if not 0 < self.guidance <= 20:
            raise ValueError("Guidance must be between 0 and 20")
        if not 1 <= self.steps <= 150:
            raise ValueError("Steps must be between 1 and 150")

@dataclass
class BatchJob:
    prompts: List[str]
    base_params: GenerationParams
    name: str
    status: str = "pending"

    def validate(self):
        """Validate batch job parameters"""
        if not self.prompts:
            raise ValueError("Batch job must contain at least one prompt")
        if not self.name:
            raise ValueError("Batch job must have a name")
        self.base_params.validate()

# ----------------------------
# Utility Functions
# ----------------------------

def setup_logging():
    """Setup logging configuration with better error handling"""
    try:
        logs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
        os.makedirs(logs_dir, exist_ok=True)

        log_file = os.path.join(logs_dir, 'flux_generator.log')

        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
            handlers=[
                logging.handlers.RotatingFileHandler(
                    log_file,
                    maxBytes=1024*1024,
                    backupCount=5,
                    encoding='utf-8'
                ),
                logging.StreamHandler(sys.stdout)
            ]
        )

        logger = logging.getLogger('FluxGenerator')
        logger.info('Logging initialized')
        logger.info(f'Log file location: {log_file}')
        return logger
    except Exception as e:
        print(f"Failed to initialize logging: {str(e)}")
        raise

# ----------------------------
# Utility Classes
# ----------------------------

class PresetManager:
    def __init__(self, presets_file="presets.json"):
        self.presets_file = presets_file
        self.presets = self.load_presets()
        self.logger = logging.getLogger('FluxGenerator')
        self.logger.info("PresetManager initialized")

    def load_presets(self):
        """Load presets with improved error handling"""
        try:
            if os.path.exists(self.presets_file):
                with open(self.presets_file, 'r') as f:
                    content = f.read().strip()
                    if content:
                        return json.loads(content)
        except Exception as e:
            self.logger.error(f"Error loading presets: {str(e)}")

        # Default presets
        return {
            "Default": {
                "width": 1024,
                "height": 768,
                "safety_tolerance": 2,
                "guidance": 2.5,
                "steps": 40
            },
            "High Quality": {
                "width": 1440,
                "height": 1024,
                "safety_tolerance": 2,
                "guidance": 3.0,
                "steps": 60
            },
            "Quick Draft": {
                "width": 512,
                "height": 512,
                "safety_tolerance": 2,
                "guidance": 2.0,
                "steps": 20
            }
        }

class FluxAPI:
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "https://api.bfl.ml/v1"
        self.headers = {
            "Content-Type": "application/json",
            "X-Key": api_key
        }
        self.logger = logging.getLogger('FluxGenerator')
        self.logger.info("FluxAPI initialized")

    def generate_image(self, model: str, params: dict) -> str:
        """Generate image with improved error handling"""
        self.logger.info(f"Generating image with model: {model}")
        try:
            url = f"{self.base_url}/{model}"
            response = requests.post(url, json=params, headers=self.headers, timeout=30)
            response.raise_for_status()
            task_id = response.json()["id"]
            self.logger.info(f"Image generation task created: {task_id}")
            return task_id
        except requests.exceptions.Timeout:
            self.logger.error("API request timed out")
            raise TimeoutError("API request timed out")
        except requests.exceptions.RequestException as e:
            self.logger.error(f"API request failed: {str(e)}")
            raise

    def get_result(self, task_id: str) -> dict:
        """Get the result of the image generation task"""
        self.logger.info(f"Fetching result for task ID: {task_id}")
        try:
            url = f"{self.base_url}/get_result?id={task_id}"
            response = requests.get(url, headers=self.headers, timeout=30)
            response.raise_for_status()
            result = response.json()
            self.logger.debug(f"API response: {result}")
            return result
        except requests.exceptions.Timeout:
            self.logger.error("API request timed out")
            raise TimeoutError("API request timed out")
        except requests.exceptions.RequestException as e:
            self.logger.error(f"API request failed: {str(e)}")
            raise

# ----------------------------
# GUI Components
# ----------------------------

class ImagePreview:
    def __init__(self, parent):
        self.parent = parent
        self.image_label = ctk.CTkLabel(parent)
        self.image_label.pack(fill=tk.BOTH, expand=True)

    def update_image(self, image_path):
        image = Image.open(image_path)
        image.thumbnail((800, 600))
        self.photo = ImageTk.PhotoImage(image)
        self.image_label.configure(image=self.photo)

class GalleryView:
    def __init__(self, parent):
        self.parent = parent
        self.canvas = ctk.CTkCanvas(parent)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.images = []

    def load_directory(self, directory):
        for file in os.listdir(directory):
            if file.lower().endswith(('.png', '.jpg', '.jpeg')):
                self.add_image(os.path.join(directory, file))

    def add_image(self, image_path):
        image = Image.open(image_path)
        image.thumbnail((150, 150))
        photo = ImageTk.PhotoImage(image)
        self.images.append(photo)
        self.canvas.create_image(10 + len(self.images)*160, 10, anchor=tk.NW, image=photo)

# ----------------------------
# Main Application Class
# ----------------------------

class FluxImageGenerator:
    def __init__(self):
        self.logger = logging.getLogger('FluxGenerator')
        self.logger.info("Initializing FluxImageGenerator")

        self.ensure_files_exist()
        self.config = self.load_config()
        self.preset_manager = PresetManager()
        self.api = FluxAPI(self.config.get('Settings', 'api_key', fallback=''))

        self.root = ctk.CTk()
        self.root.title("FLUX Image Generator Pro")
        self.root.geometry("1400x900")
        ctk.set_appearance_mode(self.config.get('Settings', 'theme', fallback='dark'))

        self.initialize_variables()

        self.task_queue = queue.Queue()
        self.batch_queue = queue.Queue()
        self.history = self.load_history()
        self.favorite_prompts = self.load_favorite_prompts()

        self.create_gui()
        self.start_workers()

    def ensure_files_exist(self):
        """Ensure necessary files and directories exist"""
        os.makedirs("logs", exist_ok=True)
        os.makedirs("output", exist_ok=True)
        if not os.path.exists("history.json"):
            with open("history.json", "w") as f:
                json.dump([], f)
        if not os.path.exists("favorites.json"):
            with open("favorites.json", "w") as f:
                json.dump([], f)

    def load_config(self):
        """Load configuration from config file"""
        self.logger.debug("Loading configuration")
        config = configparser.ConfigParser()

        if os.path.exists('config.ini'):
            try:
                config.read('config.ini')
                self.logger.info("Configuration loaded successfully")
            except Exception as e:
                self.logger.error(f"Error loading config: {str(e)}")

        # Ensure Settings section exists
        if 'Settings' not in config:
            config['Settings'] = {
                'api_key': '',
                'theme': 'dark',
                'output_directory': 'output'
            }
            self.logger.info("Created default configuration")
            self.save_config(config)

        return config

    def save_config(self, config=None):
        """Save configuration to file"""
        if config is None:
            config = self.config

        try:
            with open('config.ini', 'w') as f:
                config.write(f)
            self.logger.info("Configuration saved successfully")
        except Exception as e:
            self.logger.error(f"Error saving config: {str(e)}")
            raise

    def initialize_variables(self):
        self.logger.debug("Initializing variables")
        self.api_key = tk.StringVar(value=self.config.get('Settings', 'api_key', fallback=''))
        self.selected_model = tk.StringVar(value="flux-pro-1.1")
        self.current_preset = tk.StringVar(value="Default")
        self.theme_var = tk.StringVar(value=self.config.get('Settings', 'theme', fallback='dark'))
        self.batch_mode = tk.BooleanVar(value=False)
        self.auto_save = tk.BooleanVar(value=True)
        self.batch_continue_on_error = tk.BooleanVar(value=True)
        self.output_dir = tk.StringVar(value=self.config.get('Settings', 'output_directory', fallback='output'))

        # Initialize parameter variables
        preset = self.preset_manager.presets["Default"]
        self.width_var = tk.StringVar(value=str(preset["width"]))
        self.height_var = tk.StringVar(value=str(preset["height"]))
        self.safety_tolerance_var = tk.StringVar(value=str(preset["safety_tolerance"]))
        self.guidance_var = tk.StringVar(value=str(preset["guidance"]))
        self.steps_var = tk.StringVar(value=str(preset["steps"]))

        self.prompt_upsampling_var = tk.BooleanVar(value=False)
        self.raw_mode_var = tk.BooleanVar(value=False)
        self.aspect_ratio_var = tk.StringVar(value="16:9")
        self.output_format_var = tk.StringVar(value="jpeg")

    def create_gui(self):
        self.logger.debug("Creating GUI")
        # Create notebook for tabs
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Create tabs
        self.create_generator_tab()
        self.create_batch_tab()
        self.create_gallery_tab()
        self.create_settings_tab()

        # Create menu
        self.create_menu()

        # Create status bar
        self.create_status_bar()

        self.logger.info("GUI created successfully")

    def create_generator_tab(self):
        self.logger.debug("Creating generator tab")
        generator_frame = ctk.CTkFrame(self.notebook)
        self.notebook.add(generator_frame, text="Generator")

        # Split into left and right panels
        left_panel = ctk.CTkFrame(generator_frame)
        left_panel.pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)

        # Model selection
        model_frame = ctk.CTkFrame(left_panel)
        model_frame.pack(fill=tk.X, pady=2)
        ctk.CTkLabel(model_frame, text="Model:").pack(side=tk.LEFT, padx=5)
        models = ["flux-pro-1.1", "flux-pro", "flux-dev", "flux-pro-1.1-ultra"]
        ctk.CTkOptionMenu(model_frame, variable=self.selected_model,
                          values=models).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        # Prompt frame
        prompt_frame = ctk.CTkFrame(left_panel)
        prompt_frame.pack(fill=tk.X, padx=5, pady=5)

        ctk.CTkLabel(prompt_frame, text="Prompt:").pack(anchor=tk.W, padx=5)
        self.prompt_text = ctk.CTkTextbox(prompt_frame, height=100)
        self.prompt_text.pack(fill=tk.X, padx=5, pady=5)

        # Parameters frame
        params_frame = ctk.CTkFrame(left_panel)
        params_frame.pack(fill=tk.X, padx=5, pady=5)
        self.create_parameter_widgets(params_frame)

        # Generate button
        generate_frame = ctk.CTkFrame(left_panel)
        generate_frame.pack(fill=tk.X, padx=5, pady=5)
        ctk.CTkButton(generate_frame, text="Generate Image",
                      command=self.generate_image).pack(fill=tk.X, padx=5)

        # Right panel for preview
        right_panel = ctk.CTkFrame(generator_frame)
        right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Add image preview
        self.preview = ImagePreview(right_panel)

    def create_parameter_widgets(self, parent):
        """Create parameter widgets with validation"""
        try:
            # Width
            width_frame = ctk.CTkFrame(parent)
            width_frame.pack(fill=tk.X, padx=5, pady=2)
            ctk.CTkLabel(width_frame, text="Width:").pack(side=tk.LEFT)
            width_entry = ctk.CTkEntry(width_frame, textvariable=self.width_var)
            width_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

            # Height
            height_frame = ctk.CTkFrame(parent)
            height_frame.pack(fill=tk.X, padx=5, pady=2)
            ctk.CTkLabel(height_frame, text="Height:").pack(side=tk.LEFT)
            height_entry = ctk.CTkEntry(height_frame, textvariable=self.height_var)
            height_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

            # Safety Tolerance
            safety_frame = ctk.CTkFrame(parent)
            safety_frame.pack(fill=tk.X, padx=5, pady=2)
            ctk.CTkLabel(safety_frame, text="Safety:").pack(side=tk.LEFT)
            safety_entry = ctk.CTkEntry(safety_frame, textvariable=self.safety_tolerance_var)
            safety_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

            # Guidance
            guidance_frame = ctk.CTkFrame(parent)
            guidance_frame.pack(fill=tk.X, padx=5, pady=2)
            ctk.CTkLabel(guidance_frame, text="Guidance:").pack(side=tk.LEFT)
            guidance_entry = ctk.CTkEntry(guidance_frame, textvariable=self.guidance_var)
            guidance_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

            # Steps
            steps_frame = ctk.CTkFrame(parent)
            steps_frame.pack(fill=tk.X, padx=5, pady=2)
            ctk.CTkLabel(steps_frame, text="Steps:").pack(side=tk.LEFT)
            steps_entry = ctk.CTkEntry(steps_frame, textvariable=self.steps_var)
            steps_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

            # Seed
            seed_frame = ctk.CTkFrame(parent)
            seed_frame.pack(fill=tk.X, padx=5, pady=2)
            ctk.CTkLabel(seed_frame, text="Seed:").pack(side=tk.LEFT)
            self.seed_var = tk.StringVar(value="")
            seed_entry = ctk.CTkEntry(seed_frame, textvariable=self.seed_var)
            seed_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        except Exception as e:
            self.logger.error(f"Error creating parameter widgets: {str(e)}")
            raise

    def create_batch_tab(self):
        self.logger.debug("Creating batch tab")
        batch_frame = ctk.CTkFrame(self.notebook)
        self.notebook.add(batch_frame, text="Batch Processing")

        # Split into left and right panels
        left_panel = ctk.CTkFrame(batch_frame)
        left_panel.pack(side=tk.LEFT, fill=tk.BOTH, padx=5, pady=5)

        # Prompt input
        ctk.CTkLabel(left_panel, text="Enter prompts (one per line):").pack(anchor=tk.W, padx=5)
        self.batch_text = ctk.CTkTextbox(left_panel, height=200)
        self.batch_text.pack(fill=tk.X, padx=5, pady=5)

        # Batch settings
        settings_frame = ctk.CTkFrame(left_panel)
        settings_frame.pack(fill=tk.X, padx=5, pady=5)

        ctk.CTkCheckBox(settings_frame, text="Continue on Error",
                        variable=self.batch_continue_on_error).pack(side=tk.LEFT, padx=5)
        ctk.CTkCheckBox(settings_frame, text="Auto-save Results",
                        variable=self.auto_save).pack(side=tk.LEFT, padx=5)

        # Start button
        ctk.CTkButton(left_panel, text="Start Batch Processing",
                      command=self.start_batch_processing).pack(fill=tk.X, padx=5, pady=5)

        # Right panel for progress
        right_panel = ctk.CTkFrame(batch_frame)
        right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Progress bar
        self.batch_progress = ttk.Progressbar(right_panel, mode='determinate')
        self.batch_progress.pack(fill=tk.X, padx=5, pady=5)

        # Status label
        self.batch_status_label = ctk.CTkLabel(right_panel, text="Ready")
        self.batch_status_label.pack(padx=5)

    def create_gallery_tab(self):
        self.logger.debug("Creating gallery tab")
        gallery_frame = ctk.CTkFrame(self.notebook)
        self.notebook.add(gallery_frame, text="Gallery")

        # Add gallery view
        self.gallery_view = GalleryView(gallery_frame)

        # Load existing images
        if os.path.exists("output"):
            self.gallery_view.load_directory("output")

    def create_settings_tab(self):
        self.logger.debug("Creating settings tab")
        settings_frame = ctk.CTkFrame(self.notebook)
        self.notebook.add(settings_frame, text="Settings")

        # API Key
        api_frame = ctk.CTkFrame(settings_frame)
        api_frame.pack(fill=tk.X, padx=5, pady=5)

        ctk.CTkLabel(api_frame, text="API Key:").pack(side=tk.LEFT, padx=5)
        self.api_key_entry = ctk.CTkEntry(api_frame, textvariable=self.api_key, show="*")
        self.api_key_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        # Show/Hide API key button
        ctk.CTkButton(api_frame, text="Show/Hide",
                      command=self.toggle_api_key_visibility).pack(side=tk.RIGHT, padx=5)

        # Theme selection
        theme_frame = ctk.CTkFrame(settings_frame)
        theme_frame.pack(fill=tk.X, padx=5, pady=5)

        ctk.CTkLabel(theme_frame, text="Theme:").pack(side=tk.LEFT, padx=5)
        ctk.CTkOptionMenu(theme_frame, variable=self.theme_var,
                          values=["dark", "light"],
                          command=self.change_theme).pack(side=tk.LEFT, padx=5)

        # Save button
        ctk.CTkButton(settings_frame, text="Save Settings",
                      command=self.save_settings).pack(fill=tk.X, padx=5, pady=10)

    def create_menu(self):
        self.logger.debug("Creating menu")
        menu_bar = tk.Menu(self.root)
        file_menu = tk.Menu(menu_bar, tearoff=0)
        file_menu.add_command(label="Exit", command=self.root.quit)
        menu_bar.add_cascade(label="File", menu=file_menu)
        self.root.config(menu=menu_bar)

    def create_status_bar(self):
        self.logger.debug("Creating status bar")
        self.status_var = tk.StringVar()
        self.status_var.set("Ready")
        status_bar = ctk.CTkLabel(self.root, textvariable=self.status_var)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    def start_workers(self):
        """Start background worker threads"""
        self.logger.info("Starting worker threads")
        self.task_thread = threading.Thread(target=self.process_task_queue, daemon=True)
        self.task_thread.start()

        self.batch_thread = threading.Thread(target=self.process_batch_queue, daemon=True)
        self.batch_thread.start()

    def process_task_queue(self):
        """Process tasks in the queue with enhanced logging"""
        self.logger.info("Starting task queue processor")
        while True:
            try:
                task = self.task_queue.get()
                if task is None:
                    break

                try:
                    self.logger.info(f"Processing task: {task.prompt[:50]}...")
                    self.status_var.set("Preparing generation request...")

                    # Get API parameters
                    params = {
                        "prompt": task.prompt,
                        "width": task.width,
                        "height": task.height,
                        "safety_tolerance": task.safety_tolerance,
                        "guidance": task.guidance,
                        "steps": task.steps,
                        "prompt_upsampling": task.prompt_upsampling,
                        "output_format": task.output_format
                    }

                    if task.seed is not None:
                        params["seed"] = task.seed

                    self.logger.debug(f"API parameters: {params}")
                    self.status_var.set("Submitting to API...")

                    # Generate image
                    task_id = self.api.generate_image(
                        self.selected_model.get(),
                        params
                    )

                    self.logger.info(f"Task submitted with ID: {task_id}")
                    self.status_var.set("Processing image...")

                    # Monitor task with retries
                    retry_count = 0
                    max_retries = 60  # Adjust as needed
                    sleep_time = 5    # Time to wait between retries in seconds

                    while retry_count < max_retries:
                        result = self.api.get_result(task_id)
                        self.logger.debug(f"API response: {result}")
                        self.logger.debug(f"Task status: {result['status']}")

                        if result["status"] == "Ready":
                            self.logger.info("Image generation completed")
                            self.save_generated_image(result)
                            self.status_var.set("Image generated successfully!")
                            # Update preview if available
                            if hasattr(self, 'preview'):
                                latest_image = sorted(
                                    [f for f in os.listdir("output") if f.endswith(('.png', '.jpg', '.jpeg'))],
                                    key=lambda x: os.path.getctime(os.path.join("output", x))
                                )[-1]
                                self.preview.update_image(os.path.join("output", latest_image))
                            break
                        elif result["status"] == "Failed":
                            error_msg = result.get('error', 'Unknown error')
                            self.logger.error(f"Generation failed: {error_msg}")
                            self.status_var.set(f"Generation failed: {error_msg}")
                            break
                        else:
                            self.logger.info(f"Task {task_id} is still processing.")
                            self.status_var.set(f"Task {task_id} is still processing... ({retry_count + 1}/{max_retries})")
                            time.sleep(sleep_time)
                            retry_count += 1

                    if retry_count >= max_retries:
                        self.logger.error(f"Task {task_id} timed out after {max_retries * sleep_time} seconds")
                        self.status_var.set(f"Task {task_id} timed out.")

                    self.task_queue.task_done()

                except Exception as e:
                    self.logger.error(f"Task processing error: {str(e)}\n{traceback.format_exc()}")
                    self.status_var.set(f"Error: {str(e)}")
                    self.task_queue.task_done()

            except Exception as e:
                self.logger.error(f"Queue processing error: {str(e)}\n{traceback.format_exc()}")
                continue

    def process_batch_queue(self):
        """Process the batch queue"""
        self.logger.info("Batch queue processor started")
        while True:
            try:
                job = self.batch_queue.get()
                if job is None:
                    break

                self.logger.info(f"Processing batch job: {job.name}")
                for i, prompt in enumerate(job.prompts, 1):
                    try:
                        params = job.base_params
                        params.prompt = prompt
                        self.task_queue.put(params)
                        progress = (i / len(job.prompts)) * 100
                        self.batch_progress['value'] = progress
                        self.batch_status_label.configure(
                            text=f"Processing {i}/{len(job.prompts)} ({progress:.1f}%)")
                    except Exception as e:
                        self.logger.error(f"Error in batch processing: {str(e)}")
                        if not self.batch_continue_on_error.get():
                            break

                self.batch_status_label.configure(text="Batch processing completed")
                self.batch_queue.task_done()

            except Exception as e:
                self.logger.error(f"Batch queue error: {str(e)}")
                continue

    def load_history(self):
        """Load generation history"""
        self.logger.debug("Loading history")
        if os.path.exists('history.json'):
            try:
                with open('history.json', 'r') as f:
                    content = f.read().strip()
                    return json.loads(content) if content else []
            except json.JSONDecodeError as e:
                self.logger.error(f"Error loading history: {str(e)}")
            return []
        self.logger.info("No history file found, starting fresh")
        return []

    def load_favorite_prompts(self):
        """Load favorite prompts"""
        self.logger.debug("Loading favorite prompts")
        if os.path.exists('favorites.json'):
            try:
                with open('favorites.json', 'r') as f:
                    content = f.read().strip()
                return json.loads(content) if content else []
            except json.JSONDecodeError as e:
                self.logger.error(f"Error loading favorites: {str(e)}")
            return []
        self.logger.info("No favorites file found, starting fresh")
        return []

    def change_theme(self, theme):
        """Change the application theme"""
        ctk.set_appearance_mode(theme)
        self.logger.info(f"Theme changed to {theme}")
        # Update the config
        self.config.set('Settings', 'theme', theme)
        self.save_config()

    def toggle_api_key_visibility(self):
        current = self.api_key_entry.cget("show")
        self.api_key_entry.configure(show="" if current == "*" else "*")

    def save_settings(self):
        """Save settings to configuration"""
        self.logger.info("Saving settings")
        self.config.set('Settings', 'api_key', self.api_key.get())
        self.config.set('Settings', 'theme', self.theme_var.get())
        self.save_config()

    def generate_image(self):
        """Generate single image with enhanced error handling"""
        try:
            self.logger.info("Starting image generation")

            if not self.api_key.get():
                self.logger.error("No API key provided")
                messagebox.showerror("Error", "Please enter your API key in Settings")
                return

            prompt = self.prompt_text.get("1.0", tk.END).strip()
            if not prompt:
                self.logger.error("No prompt provided")
                messagebox.showerror("Error", "Please enter a prompt")
                return

            # Validate dimensions
            try:
                width = int(self.width_var.get())
                height = int(self.height_var.get())
                if width % 32 != 0 or height % 32 != 0:
                    self.logger.error(f"Invalid dimensions: {width}x{height}")
                    messagebox.showerror("Error", "Width and height must be multiples of 32")
                    return
            except ValueError:
                self.logger.error("Invalid width or height value")
                messagebox.showerror("Error", "Width and height must be integers")
                return

            # Validate other parameters
            try:
                safety_tolerance = int(self.safety_tolerance_var.get())
                guidance = float(self.guidance_var.get())
                steps = int(self.steps_var.get())
            except ValueError:
                self.logger.error("Invalid parameter values")
                messagebox.showerror("Error", "Safety Tolerance, Guidance, and Steps must be numbers")
                return

            # Create parameters
            params = GenerationParams(
                prompt=prompt,
                width=width,
                height=height,
                safety_tolerance=safety_tolerance,
                guidance=guidance,
                steps=steps,
                prompt_upsampling=self.prompt_upsampling_var.get(),
                raw_mode=self.raw_mode_var.get(),
                output_format=self.output_format_var.get()
            )

            # Handle seed
            if self.seed_var.get():
                try:
                    params.seed = int(self.seed_var.get())
                except ValueError:
                    self.logger.error("Invalid seed value")
                    messagebox.showerror("Error", "Seed must be an integer")
                    return

            self.logger.info(f"Queueing generation task with prompt: {prompt[:50]}...")
            self.status_var.set("Generating image...")
            self.task_queue.put(params)

        except Exception as e:
            self.logger.error(f"Error in generate_image: {str(e)}\n{traceback.format_exc()}")
            messagebox.showerror("Error", f"An error occurred: {str(e)}")

    def save_generated_image(self, result):
        """Save generated image by downloading from the provided URL"""
        try:
            # Ensure output directory exists
            os.makedirs("output", exist_ok=True)

            # Save image
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"generated_{timestamp}.{self.output_format_var.get()}"
            filepath = os.path.join("output", filename)

            self.logger.info(f"Saving image to: {filepath}")

            # Get the image URL from the result
            image_url = result["result"]["sample"]

            # Download the image
            response = requests.get(image_url, stream=True)
            response.raise_for_status()

            with open(filepath, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            # Add to history
            self.history.append({
                "filename": filename,
                "params": result["result"].get("params", {}),
                "timestamp": timestamp
            })

            # Save history
            with open("history.json", "w") as f:
                json.dump(self.history, f, indent=2)

            # Update gallery if available
            if hasattr(self, 'gallery_view'):
                self.gallery_view.add_image(filepath)

            self.logger.info("Image saved successfully")

        except Exception as e:
            self.logger.error(f"Error saving image: {str(e)}\n{traceback.format_exc()}")
            messagebox.showerror("Error", f"Failed to save image: {str(e)}")

    def start_batch_processing(self):
        """Start processing batch jobs"""
        self.logger.info("Starting batch processing")
        # Extract prompts from the batch text input
        prompts = self.batch_text.get("1.0", tk.END).strip().split("\n")
        if not prompts or prompts == [""]:
            messagebox.showerror("Error", "No prompts provided for batch processing")
            return

        # Validate and convert parameters
        try:
            width = int(self.width_var.get())
            height = int(self.height_var.get())
            safety_tolerance = int(self.safety_tolerance_var.get())
            guidance = float(self.guidance_var.get())
            steps = int(self.steps_var.get())
        except ValueError:
            self.logger.error("Invalid parameter values for batch job")
            messagebox.showerror("Error", "Width, Height, Safety Tolerance, Guidance, and Steps must be valid numbers")
            return

        # Create a batch job with the extracted prompts
        base_params = GenerationParams(
            width=width,
            height=height,
            safety_tolerance=safety_tolerance,
            guidance=guidance,
            steps=steps,
            output_format=self.output_format_var.get()
        )
        job_name = f"Batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        batch_job = BatchJob(prompts=prompts, base_params=base_params, name=job_name)

        # Add the batch job to the queue
        self.batch_queue.put(batch_job)
        self.logger.info(f"Batch job '{job_name}' added to queue")
        self.batch_status_label.configure(text="Batch job queued")

    def run(self):
        """Start the application"""
        self.logger.info("Starting application")
        try:
            # Create necessary directories
            os.makedirs("output", exist_ok=True)

            # Start main loop
            self.root.mainloop()

        except Exception as e:
            self.logger.critical(f"Application error: {str(e)}\n{traceback.format_exc()}")
            raise

# ----------------------------
# Main Execution Block
# ----------------------------

def main():
    """Main entry point with error handling"""
    try:
        logger = setup_logging()
        logger.info("Starting FluxImageGenerator application")
        print(f"Log file can be found at: {os.path.abspath(os.path.join('logs', 'flux_generator.log'))}")
        app = FluxImageGenerator()
        app.run()
    except Exception as e:
        logger = logging.getLogger('FluxGenerator')
        logger.critical(f"Application failed to start: {str(e)}\n{traceback.format_exc()}")
        messagebox.showerror("Critical Error", f"Application failed to start: {str(e)}")
        raise

if __name__ == "__main__":
    main()
