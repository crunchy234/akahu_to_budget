import sys
import os

# Add your project directory to the sys.path
PROJECT_HOME = '/home/lakeland/akahu_to_budget/'
if PROJECT_HOME not in sys.path:
    sys.path.insert(0, PROJECT_HOME)

# Activate the virtual environment
ACTIVATE_ENV = os.path.join(PROJECT_HOME, '.venv', 'bin', 'activate_this.py')
with open(ACTIVATE_ENV, encoding='utf-8') as file_:
    exec(file_.read(), {'__file__': ACTIVATE_ENV})

# Load environment variables from .env
ENV_PATH = os.path.join(PROJECT_HOME, '.env')
if os.path.exists(ENV_PATH):
    with open(ENV_PATH, encoding='utf-8') as f:
        for line in f:
            if '=' in line:
                # Split key and value, strip whitespace, and remove surrounding quotes if present
                key, value = map(str.strip, line.split('=', 1))
                if value.startswith('"') and value.endswith('"'):
                    value = value[1:-1]  # Remove surrounding quotes
                os.environ[key] = value

# Import the Flask app instance
from flask_app import application
