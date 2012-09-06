google-drive-tidy
=================

Description
-----------

Retrieve your Google Drive documents list and folder hierarchy.


Updating
--------

Before running this tool you need to create a valid client-secrets.json that
allows the application to authenticate and talk with the Google API.

This can be created following instructions at:
https://code.google.com/apis/console

Tested with Python 2.7

```sh
virtualenv env
source env/bin/activate
easy_install httplib2
easy_install google_api_python_client
python google-drive-tidy.py
```


Contributor list
----------------

@james_austin
