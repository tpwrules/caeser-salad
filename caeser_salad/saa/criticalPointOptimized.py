#py -3.6 -m pip install pyrealsense2
#py -3.6 filename.py
#can either just run file or run init_Camera()
# #10% is cutoff

import pyrealsense2 as rs
import time
import numpy

import asyncio
  
async def readCamera(pipeline, status):
  try:
    #the following two lines relate to finding the execution time and can be removed once tested on final hardware
    testTime=time.monotonic()
    prevTime=0
    while(True):
      #code for finding the time it takes to execute the loop. Can be remove once tested on final hardware
      prevTime=testTime
      testTime=time.monotonic()
      diff=testTime-prevTime

      await asyncio.sleep(0.2-diff) 
      criticalCount=0 #ammount of points in a dangerous distance
      leftCount=0 #ammount of critical points on left side
      rightCount=0 #ammount of critical points on right side
      bottomCutoff=0.15*1000 #critical distance range min to ignore erroneous measurements
      topCutoff=1.3*1000 #critical distance range max
      totalCutoffPercent=17.5 #percentage of total count to consider crashing
      LRCutoffPercent=12.5 #percentage of left right count to consider crashing
      frames=pipeline.wait_for_frames()
      depth=frames.get_depth_frame()
      criticalArray=numpy.asanyarray(depth.get_data())
      
      criticalArray=(criticalArray>bottomCutoff) & (criticalArray<topCutoff)
      criticalCount=numpy.sum(criticalArray)
      #print(criticalArray[:480,:320].shape)
      leftCount=numpy.sum(criticalArray[:480,:320])
      rightCount=numpy.sum(criticalArray[:480,320:640])
      criticalPercent=100*criticalCount/(480*640) #find critical point percentage over all pixels
      leftPercent=100*leftCount/(480*320) #find critical point percentage of left side
      rightPercent=100*rightCount/(480*320) #find critical point percentage of right side
      if(criticalPercent>totalCutoffPercent or leftPercent>LRCutoffPercent or rightPercent>LRCutoffPercent): #critical cutoff is set to 15
        if(leftPercent>rightPercent):
          status("left")
        else:
          status("right")
      else:
        status("okay")
      
      print("Total count: "+str(criticalPercent)+"   Left count: "+str(leftPercent)+"   Right count: "+str(rightPercent)+"\n") 
  except Exception as e:
    print(e)
    pass

async def init_Camera(status):
  try:
    pipeline=rs.pipeline()
    config = rs.config()
    config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)
    pipeline.start(config)
    print("started")
    await readCamera(pipeline, status)
  except Exception as e:
    print(e)
    pass
