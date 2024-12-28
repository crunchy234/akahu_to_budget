# This file contains the WSGI configuration required to serve up your
# web application at http://<your-username>.pythonanywhere.com/
# It works by setting the variable 'application' to a WSGI handler of some
# description.
#
# The below has been auto-generated for your Flask project
"""
Module docstring
"""
import sys
import os

# Add your project directory to the sys.path
PROJECT_HOME = '/home/lakeland/akahu_to_budget/'
if PROJECT_HOME not in sys.path:
    sys.path = [PROJECT_HOME] + sys.path

# Activate the virtual environment
# Path to the virtualenv you want to use
ACTIVATE_ENV = os.path.expanduser('//home/lakeland/akahu_to_budget/.venv/bin/activate_this.py')
# Execute the script to activate the virtual environment
with open(ACTIVATE_ENV, encoding='utf-8') as file_:
    exec(file_.read(), {'__file__': ACTIVATE_ENV})

# Path to your .env file
ENV_PATH = '/home/lakeland/akahu_to_budget/.env'
# Check if the .env file exists
if os.path.exists(ENV_PATH):
    with open(ENV_PATH, encoding='utf-8') as f:
        for line in f:
            # Parse each line as an environment variable
            if '=' in line:
                # Remove leading/trailing whitespace, split by first '=', and strip each part
                key, value = map(str.strip, line.split('=', 1))
                os.environ[key] = value

# Import Flask app, but need to call it "application" for WSGI to work
from flask_app import app as application_func  # Import the function
application = application_func()  # Call the function to get the Flask app instance
