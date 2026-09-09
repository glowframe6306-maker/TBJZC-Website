from backend.app import app

# Keep the serverless entry point as a thin wrapper around the real Flask app.
# This preserves the public website routes while exposing the admin CMS APIs.

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
