# What We Are Doing
We are creating a system where my wheeled rover has a nRF9151 cellular modem that sends about 11 different data points (Latitude, Longitude, Accuracy, Altitude, Altitude Accuracy, SPeed, Speed Accuracy, V. speed, V. speed accuracy, Heading, Heading accuracy, Date, Time (UTC), PDOP, HDOP, VDOP, TDOP) every second while it is moving around in the environment. Also sends LSM6DS3 IMU data (16 bits each of gyroscope x,y,z and acceleration x,y,z) atleast once per second. Also sends motor encoder data probably more than once per second. Ultimately data sent to the main server, which is my windows laptop. From my laptop I will see the live data from my robot with GlobalRTS. I can then use my laptop to click on certain areas on GlobalRTS's Google Earth-like UI to command the robot to go a certain coordinate. Pretty simple setup really. I just control robot with laptop and it sends information to my laptop in real time. 

## Laptop
Basically a way to open GlobalRTS, which I am going to assume is a browser on the internet.

## GlobalRTS
GlobalRTS is the UI interface to see the live location and data from robot. I can also use it to send commands to the robot like telling it where to go. This is done by giving GlobalRTS a Google Earth view so I can click on the rover from the map and then click on a location to send it to. Possible since the Google Earth map is already divided into Latitude/Longitude coordinates, so both the laptop, GlobalRTS, and robot can agree on coordinates and where things are. 

Important to note the GlobalRTS is also a way for me to check the news, Oura Ring sleep calendar, and has RTS controls like left click+drag to select units (robots), left click on a unit to select it, once selected right click on a location to send it there and displays the location selected, also control panel that can show/hide the different panels and UI elements.

## Miraeopus.com
I bought and own the domain name Miraeopus.com. Probably a good place to host GlobalRTS and be the connector between my laptop and rover.

## Robot
First version will have bare minimum a wheeled rover body I bought online, can turn, go, stop, has a nRF9151-DK so can process motor control loop, send motor encoder data, send IMU data, atleast once per second. Can also react to controls given by my laptop through GlobalRTS.