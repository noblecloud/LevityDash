from scipy.ndimage import gaussian_filter1d
import matplotlib.pyplot as plt
from numpy import random
import matplotlib
from datetime import datetime
from classes.constants import Colors
# stringDates = [value.strftime('%Y%m%d') for value in dateArray]

# import pylab

from classes.constants import fields
from classes.forecast import *
import classes.display

lat, lon = 37.40834, -76.54845
key = "q2W59y2MsmBLqmxbw34QGdtS5hABEwLl"

forecast = hourlyForecast(key, (lat, lon), 'hourly', measurementFields=['temp', 'precipitation', 'sunrise', 'sunset',
																		'feels_like', 'dewpoint'])
#
# print(forecast['temp'])
# print(forecast[0])

# for x in forecast:
# 	print(x)



print(device[0].last_data)
outdoorTempValue 	= device[0].last_data['tempf']
outdoorDewpoint 	= device[0].last_data['dewPoint']
outdoorFeels 		= device[0].last_data['feelsLike']

indoorTempValue 	= device[0].last_data['tempinf']
indoorDewpointValue = device[0].last_data['dewPointin']

# forecast = forecast(key,['nowcast', 'hourly'], measurementFields=fields.HOURLY)
#
# forecast.getData(['nowcast', 'hourly'], ['temp', 'feels_like'])
# nowcast = forecast.makeFigurePix((1600, 300, 226),['nowcast'])
# hourly = forecast.makeFigurePix((1600, 300, 226), ['hourly'])

import pygame
from pygame.locals import *

pygame.init()

screenx = 1920
screeny = 1080
# screenx = 1080
# screeny = 720
dpi = 212

chunkx: int = int(screenx/24)
chunky: int = int(screeny/24)

flags = pygame.DOUBLEBUF | pygame.FULLSCREEN | pygame.HWSURFACE

window = pygame.display.set_mode((screenx, screeny), flags, display=1)
screen = pygame.display.get_surface()

#
# # nowcastSurf = pygame.image.fromstring(nowcast, size, "RGB")
# # screen.blit(nowcastSurf, (screenx - 1600, screeny - 900))

white = (255, 255, 255)
black = (0, 0, 0)
almostBlack = (50, 50, 50)
kelvin = Colors().kelvinToRGB(3000)

pygame.display.set_caption('Show Text')

largeFont = pygame.font.Font('/Library/Fonts/SF-Pro-Text-Light.otf', round(screeny / 6))
smallFont = pygame.font.Font('/Library/Fonts/SF-Pro-Text-Light.otf', round(screeny / 24))
timeFont  = pygame.font.Font('/Library/Fonts/SF-Mono-Light.otf', 	 round((chunky * 2) - 8))

topLeftRect = pygame.Rect((10, 10), (chunkx*8, chunky*4))
topLeftScreen = screen.subsurface(topLeftRect)

ctime = datetime.now().strftime('%-I:%M%p').lower()
cdate = datetime.now().strftime('%a %b %-d')
timeText = timeFont.render(ctime, True, kelvin, black)
timeTextRect = timeText.get_rect()

dateText = timeFont.render(cdate, True, kelvin, black)
dateTextRect = dateText.get_rect()
dateTextRect.top = timeTextRect.bottom

topLeftScreen.blit(timeText, timeTextRect)
topLeftScreen.blit(dateText, dateTextRect)

centerLeftRect = pygame.Rect((chunkx*8, 10), (chunkx*8, chunky*8))

outdoorTemp = largeFont.render('{}º'.format(outdoorTempValue), True, kelvin, black)
outdoorTempRect = outdoorTemp.get_rect()
outdoorTempRect.topleft = (chunkx, chunky*6)

outdoorLabel = smallFont.render("Outdoors", True, kelvin, black)
outdoorLabelRect = outdoorLabel.get_rect()
outdoorTempRect.width = round((screenx / 3) + 20)
outdoorLabelRect.center = (outdoorTempRect.centerx, outdoorTempRect.top)

indoorTemp = largeFont.render('{}º'.format(indoorTempValue), True, kelvin, black)
indoorTempRect = indoorTemp.get_rect()
indoorTempRect.width = round((screenx - 20) / 3)
indoorTempRect.topleft = (chunkx, chunky*16)

indoorLabel = smallFont.render("Indoors", True, kelvin, black)
indoorLabelRect = outdoorLabel.get_rect()
indoorLabelRect.center = (indoorTempRect.centerx, indoorTempRect.top)

screen.blit(outdoorTemp, outdoorTempRect)
screen.blit(outdoorLabel, outdoorLabelRect)
screen.blit(indoorTemp, indoorTempRect)
screen.blit(indoorLabel, indoorLabelRect)

sizex = screenx - int(outdoorLabelRect.right) - 150
sizey = round(screeny/2)
forecastDisplay = classes.display.dataDisplay(forecast, (sizex,sizey,dpi))


fig = forecastDisplay.makeFigure('raster')
hourlySurf = pygame.image.fromstring(fig, (sizex, sizey), "RGB")
screen.blit(hourlySurf, (outdoorTempRect.right - 100, -40))

pygame.display.flip()

done = False
clock = pygame.time.Clock()

while not done:

	# forecast = hourlyForecast(key, (lat, lon), 'hourly',
	# 						  measurementFields=['temp', 'precipitation', 'sunrise', 'sunset'])
	# forecastDisplay = classes.display.dataDisplay(forecast, (sizex, sizey, dpi))
	#
	# fig = forecastDisplay.makeFigurePix('test')
	# hourlySurf = pygame.image.fromstring(fig, (sizex, sizey), "RGB")
	# screen.blit(hourlySurf, (outdoorTempRect.right - 0, 40))
	#
	# ctime = datetime.now().strftime('%I:%M:%S')
	# indoorLabel = smallFont.render(ctime, True, white, black)
	# indoorLabelRect = outdoorLabel.get_rect()
	# indoorLabelRect.center = (indoorTempRect.centerx, indoorTempRect.top)
	# screen.blit(indoorLabel, indoorLabelRect)
	#
	#
	# pygame.display.flip()
	# # pygame.time.wait(5*1000)

	for event in pygame.event.get():
		if event.type == pygame.QUIT:
			done = True

	# This limits the while loop to a max of 60 times per second.
	# Leave this out and we will use all CPU we can.
	clock.tick(1)

# Be IDLE friendly
pygame.quit()
