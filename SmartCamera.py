from __future__ import print_function

import time
import math
import json

from threading import Thread
import threading

import cv2 # OpenCV

import mraa # Sensor & Actuator control
from upm import pyupm_jhd1313m1 as lcd

import paho.mqtt.client as mqtt # MQTT communication

import tweepy # Twitter API

import Person


# global variables
persons = []
personId = 1
entered = 0
exited = 0

faceCascade = cv2.CascadeClassifier('/usr/local/share/OpenCV/haarcascades/haarcascade_frontalface_default.xml')

# Twitter app credentials
# https://apps.twitter.com/
consumer_key = 'DHTPps8jjwrKvs7AurjFit1wH'
consumer_secret = 'Bc8NPcB6xKlzELwQvjr6ikBviy5e4noZdXen1V4LFIEdwaxe7e'
access_token = '460946429-bnYDAjZ8RQsR7BiKgGMGIf3LxlbvfFubqpVCTpaC'
access_token_secret = 'rZisORM5D9je6yqoimhj8sdoevNfosyPdDfJvVo7H8pbi'


# draw rectangles around detected faces
def draw_detections(img, rects, thickness=2):
    for (x, y, w, h) in rects:
        (pad_w, pad_h) = (int(0.15 * w), int(0.05 * h))
        cv2.rectangle(img, (x, y), (x + w, y + h), (0, 255, 0),thickness)


# draw rectangles around detected faces
def mark_intruder(img, x, y, w, h, date, thickness=2):
    (pad_w, pad_h) = (int(0.15 * w), int(0.05 * h))
    cv2.rectangle(img, (x, y), (x + w, y + h), (0, 0, 255),thickness)
    cv2.putText(img, str(date), (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1, cv2.LINE_AA)


# The callback for when the client receives a CONNACK response from the server.
def on_connect(client, userdata, flags, rc):
    print('Connected with result code ' + str(rc))


# save a snapshot
def save_snapshot(img):
    fileName = 'snapshots/' + time.strftime("%Y%m%d%H%M%S") + '.jpg'
    cv2.imwrite(fileName, img)
    return fileName


# SmartCamera class
class SmartCamera(object):

    def __init__(self):
        # self.video = cv2.VideoCapture('http://192.168.1.175:8080/?action=stream.mjpg')
        self.video = cv2.VideoCapture(1)

        self.w = self.video.get(3)  # CV_CAP_PROP_FRAME_WIDTH
        self.h = self.video.get(4)  # CV_CAP_PROP_FRAME_HEIGHT
        self.rangeLeft = int(1 * (self.w / 6))
        self.rangeRight = int(5 * (self.w / 6))
        self.midLine = int(3 * (self.w / 6))

        # get the first frame ready when web server starts requesting
        (_, self.rawImage) = self.video.read()
        (ret, jpeg) = cv2.imencode('.jpg', self.rawImage)
        self.frameDetections = jpeg.tobytes()

        self.contours = []

        # initialize the variable used to indicate if the thread shouldbe stopped
        self.stopped = False

        # Create MQTT client
        self.client = mqtt.Client()
        self.client.on_connect = on_connect
        # Connect to MQTT broker
        self.client.connect('broker.hivemq.com', 1883, 60)

        # authenticate Twitter app
        auth = tweepy.OAuthHandler(consumer_key, consumer_secret)
        auth.set_access_token(access_token, access_token_secret)
        # create Tweepy API
        self.api = tweepy.API(auth)

        # open connection to Firmata
        mraa.addSubplatform(mraa.GENERIC_FIRMATA, "/dev/ttyACM0")
        time.sleep(0.1)
        # create LCD instance
        self.myLcd = lcd.Jhd1313m1(512, 0x3E, 0x62)



    def __del__(self):
        self.video.release()


    # returns the frame with people detections
    def getFrameWithDetections(self):
        return self.frameDetections


    def start(self):
        # start the thread that prepares frames for output
        t = Thread(target=self.updateOutput, args=())
        t.daemon = True
        t.start()

        # start the thread that detects people
        t2 = Thread(target=self.detectPeople, args=())
        t2.daemon = True
        t2.start()

        return self


    def stop(self):
        # indicate that the thread should be stopped
        self.stopped = True


    # the thread that prepares frames for output
    def updateOutput(self):
        print('called updateOutput')
        # keep looping infinitely until the thread is stopped
        while True:
            # if the thread indicator variable is set, stop the thread
            if self.stopped:
                return

            img = self.rawImage.copy()

            # draw rectangles around the detected faces faces
            draw_detections(img, self.contours)

            # draw the boundary lines
            cv2.line(img, (int(self.rangeLeft), 0), (int(self.rangeLeft), int(self.h)), (0, 0, 255), thickness=1)
            cv2.line(img, (int(self.rangeRight), 0), (int(self.rangeRight), int(self.h)), (0, 0, 255), thickness=1)
            cv2.line(img, (int(self.midLine), 0), (int(self.midLine), int(self.h)), (255, 0, 0), thickness=1)

            # visually show the counters
            cv2.putText(img, 'Entered: ' + str(entered), (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2, cv2.LINE_AA)
            cv2.putText(img, 'Exited: ' + str(exited), (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2, cv2.LINE_AA)

            # encode the output frame
            (ret, jpeg) = cv2.imencode('.jpg', img)

            # convert output frame to a byte string and update the output
            self.frameDetections = jpeg.tobytes()


    # the thread that detects and tracks people
    def detectPeople(self):
        #keep looping infinitely until the thread is stopped
        while True:
            # if the thread indicator variable is set, stop the thread
            if self.stopped:
                return

            # read the next frame from the stream
            (self.grabbed, self.rawImage) = self.video.read()

            # convert to grayscale
            gray = cv2.cvtColor(self.rawImage, cv2.COLOR_BGR2GRAY)

            # detect faces
            faces = faceCascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30), flags=cv2.CASCADE_SCALE_IMAGE)
            self.contours = faces

            # track the people in the frame
            self.trackPeople(self.contours)


    def trackPeople(self, rects):
        global personId
        global entered
        global exited

        for (x, y, w, h) in rects:
            new = True
            xCenter = x + w / 2
            yCenter = y + h / 2
            inActiveZone = xCenter in range(self.rangeLeft, self.rangeRight)

            for (index, p) in enumerate(persons):
                dist = math.sqrt((xCenter - p.getX()) ** 2 + (yCenter - p.getY()) ** 2)
                if dist <= w / 2 and dist <= h / 2:
                    if inActiveZone:
                        new = False
                        if p.getX() < self.midLine and xCenter >= self.midLine:
                            print('person ' + str(p.getId()) + ' passed the border')
                            entered += 1

                            # send an alarm
                            self.sendAlarm(entered, x, y, w, h)


                        if p.getX() > self.midLine and xCenter <= self.midLine:
                            print('person ' + str(p.getId()) + ' is going right')
                            exited += 1

                        p.updateCoords(xCenter, yCenter)
                        break

                    else:
                        print('person ' + str(p.getId()) + ' is removed')
                        persons.pop(index)

            if new == True and inActiveZone:
                print('new person ' + str(personId) + " detected")
                p = Person.Person(personId, xCenter, yCenter)
                persons.append(p)
                personId += 1

                # publish the newly detected person with its personId and time in JSON format
                data = {"personId": personId, "time":  time.time()}
                self.client.publish('smartCamera/detections', json.dumps(data))


    def sendAlarm(self, entered, x, y, w, h):
        # these things can take long, don't block the process
        t = Thread(target=self.sendAlarmThread, args=(entered, x, y, w, h))
        t.start()


    def sendAlarmThread(self, entered, x, y, w, h):
        # send an alarm over MQTT
        self.client.publish('smartCamera/alarm', 'Someone passed the border.')

        # get a copy of the raw image
        img = self.rawImage.copy()

        # draw rectangles around the detected faces faces
        mark_intruder(img, x, y, w, h, time.strftime("%d-%m-%Y %H:%M:%S"))

        # write message on LCD
        self.myLcd.clear
        time.sleep(0.05)
        self.myLcd.setCursor(0,0)
        time.sleep(0.05)
        self.myLcd.write('Total passes:' + str(entered))

        # save a snapshot
        fileName = save_snapshot(img)

        # post a tweet with the snapshot
        self.api.update_with_media(fileName, 'Warning: Intruder detected!')
