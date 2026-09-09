import logging

from backend.app import app

logging.basicConfig(level=logging.INFO)

# Vercel Python serverless expects a WSGI app object at module scope.
# The local Flask development server must not be started here.
app = app
application = app
