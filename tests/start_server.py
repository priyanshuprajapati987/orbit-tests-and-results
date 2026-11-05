import sys

sys.path.insert(0, r"D:\JARVES")
from orbit.orbit.server import create_app

app = create_app()
app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
