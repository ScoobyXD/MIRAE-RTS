# Context
Most of the steps are here https://core-electronics.com.au/guides/raspberry-pi/raspberry-pi-4g-gps-hat/, however a few things are deprecated and different now.

## Insall
sudo apt-get install minicom
wget https://www.waveshare.com/w/upload/2/29/SIM7600X-4G-HAT-Demo.7z
sudo apt-get install p7zip-full
7z x SIM7600X-4G-HAT-Demo.7z -r -o/home/<your raspi name>/<folder you want this in>
sudo chmod 777 -R /home/<your raspi name>/<folder you want this in>SIM7600X-4G-HAT-Demo
sudo nano /etc/rc.local --create a new rc.local file because the new Raspi OS doesn't have it

write to rc.local:
#!/bin/sh -e

sleep 10
sudo sh /home/pi/SIM7600X-4G-HAT-Demo/Raspberry/c/sim7600_4G_hat_init

exit 0

Then:
sudo chmod +x /etc/rc.local
cd /home/<your raspi name>/<folder you want this in>SIM7600X-4G-HAT-Demo/Raspberry/c/bcm2835

Now in bcm2835/src/bcm2835.c you need to replace the delayMicroseconds(10); with bcm2835_delayMicroseconds(10); (there 2 on lines 531 and 533)

Save and then run:
chmod +x configure
./configure
sudo make
sudo make install
sudo reboot

## Run PhoneCall.py: (This does not work)
Go to /home/<whatever file path>/SIM7600X-4G-HAT-Demo/Raspberry/python/PhoneCall/PhoneCall.py

Edit PhoneCall.py 
Change: ser = serial.Serial('/dev/ttyS0',115200)
To: ser = serial.Serial('/dev/ttyUSB2', 115200, timeout=1)

Confirm AT port with:
sudo minicom -D /dev/ttyUSB2 -b 115200

then Type AT, should see OK

Now there is a good chance the AT port is held up by ModemManager by default, so do:
sudo systemctl stop ModemManager
sudo systemctl disable ModemManager

