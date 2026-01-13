# todo list
 - build simple cache (15 min ttl, lru eviction)
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

# query api in prod
curl https://api.buoy-data.com/buoy?id=44065 | jq

# ssh into api ec2 instance
ssh -i aws_ec2.pem ubuntu@ec2-3-94-191-77.compute-1.amazonaws.com