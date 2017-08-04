#http://www.pyimagesearch.com/2015/11/09/pedestrian-detection-opencv/
# USAGE
# python detect.py --images images

# import the necessary packages
from __future__ import print_function
from imutils.object_detection import non_max_suppression
from imutils import paths
import numpy as np
import argparse
import imutils
import cv2

import time



# initialize the HOG descriptor/person detector
hog = cv2.HOGDescriptor()
hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())

video = cv2.VideoCapture(1)

while True:
	# load the image and resize it to (1) reduce detection time
	# and (2) improve detection accuracy
	ret, image = video.read()
	image = imutils.resize(image, width=min(400, image.shape[1]))
	orig = image.copy()

	# measure time
	start_time = time.time()

	# detect people in the image
	(rects, weights) = hog.detectMultiScale(image, winStride=(4, 4),
		padding=(8, 8), scale=1.05)

	# draw the original bounding boxes
	for (x, y, w, h) in rects:
		cv2.rectangle(orig, (x, y), (x + w, y + h), (0, 0, 255), 2)

	# apply non-maxima suppression to the bounding boxes using a
	# fairly large overlap threshold to try to maintain overlapping
	# boxes that are still people
	rects = np.array([[x, y, x + w, y + h] for (x, y, w, h) in rects])
	pick = non_max_suppression(rects, probs=None, overlapThresh=0.65)



	# draw the final bounding boxes
	for (xA, yA, xB, yB) in pick:
		cv2.rectangle(image, (xA, yA), (xB, yB), (0, 255, 0), 2)


	print("--- %s seconds ---" % (time.time() - start_time))

	# show the output images
	cv2.imshow("Before NMS", orig)
	cv2.imshow("After NMS", image)
	cv2.waitKey(0)