# todo list
 - connect API to buoy fetching
 - connect IOS widget to the API, remove client-side buoy fetch logic
 - deploy the API to prod server
 - build redis cache
 - release the app to the app store
 - build widget options (configure widget outside of ios app)

# create venv
python3 -m venv venv

# activate it
source venv/bin/activate

# start flask api
python3 app.py

# ensure port 5000 is available:
Apple AirPlay Receiver listens on port 5000. While testing, disable it by navigating to: System Settings > General > AirDrop & Handoff > AirPlay Receiver (requires pw to change)

# query api locally:
curl -X GET http://localhost:5000/buoy?id=44065