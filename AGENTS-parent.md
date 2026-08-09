## project context

- buoydata is a multi-repo project that builds an iOS app (`buoy` repo) and an API service (`buoys_api` repo) that makes buoy readings more easily accessible, primarily targeted for surfers, but I'm open to other users
- the original, and still primary, motivation of this work was to build an iOS lock screen widget where users can see key buoy readings "at a glance" for checking surf conditions: swell height, period, and direction from a buoy near them
- the app itself has a Favorites view where users can select and manage their favorite buoys, and the 1st item in that list is the buoy used for the lock screen widget
- there's also a Map view that visualizes all known buoys on the map and allows users to add favorites visually
- currently, the app and API service source buoy data exclusively from the NOAA, but longer term it would be cool to add other networks of buoys
- `buoys_api` is deployed on a single ec2 instance on aws, and supports two simple services: `/buoy`, which returns readings for a single buoy, and `/stations`, which returns the full list of known active stations from the NOAA (station ID, name, and some other metadata I think, but not live readings). the API implements some simple caching so we don't bombard the NOAA with redundant requests

## deployment history

- v1.0 of the mobile app was published on the app store on Mar 11, 2026
- v1.1 was published on Mar 17, 2026. it added much more functionality: favorites view, map view
- v1.2.0 was published on Jun 6, 2026. it improved the design of the "add buoy" sheet and expanded map view to the top of the screen

## git conventions

- never push to remote or merge to main without explicit approval. assume that I will handle this normally

## development & testing

- when making iOS app changes, run lightweight Xcode compile checks as generic device builds with signing disabled and an isolated DerivedData path, but do not run simulators unless explicitly requested
- when testing API changes (`buoys_api`), you must first activate the venv before running a script or starting the flask server (e.g. `python3 src/app.py`)
- as of march 2026, I test on my iPhone 15 Pro Max which has a 6.7" screen. I'm somewhat blind as to how the UI will look on different screen sizes
- the iOS project has minimum deployment = iOS 18.0. My phone is currently on iOS 26.5 and I'm primarily targeting that version for ongoing development. No need to change our min deployment, but something to keep in mind should we consider anything incompatible with 18
