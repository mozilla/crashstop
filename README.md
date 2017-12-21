# crashstop

Library to display crash data from Socorro by build-id.

Available as a WebExtension on https://addons.mozilla.org/firefox/addon/bugzilla-crash-stop/


## Setup

Install the prerequisites via `pip`:
```sh
sudo pip install -r requirements.txt
```

## Running tests

Install test prerequisites via `pip`:
```sh
sudo pip install -r test-requirements.txt
```

Run tests:
```sh
coverage run --source=crashstop -m unittest discover tests/
```

## Bugs

https://github.com/mozilla/crashstop/issues/new

## Contact

Email: release-mgmt@mozilla.com
