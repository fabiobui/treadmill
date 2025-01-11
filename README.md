# Treadmill Flask App

## Features ##

This Flask App is an app that 
- connects to your Treadmill via bluetooth
- rebroadcasts the data as bluetooth device (name ORANGE-PI3-ZERO)
- showe an html page with data received
- saves data both on local db (Sqlite) & remote db (MySql)

## Installation ##

The **config.json** file contains the parameters to:
- connect to Treadmill 
- set the limits on widget for speed and bpm
- connect to MySql remote server **TO DO** (now is in *db_management_py*)
- connect to MQTT broker to send a *switch_off* message

## Requirements ##

- Python vers. 3.11+
- Flask module
- Bleak module for bluetooth
- SQLAlchemy for db access & management




## Contributing
Guidelines for contributing to the project.

## License
This project is licensed under the [License Name](LICENSE).



