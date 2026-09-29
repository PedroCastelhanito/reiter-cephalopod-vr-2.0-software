"""Read-only camera capability inventory: no acquisition or node writes."""
import json, pathlib, datetime
from pypylon import pylon, genicam
out=pathlib.Path(__file__).resolve().parents[1]/'evidence'
rows=[]
for d in pylon.TlFactory.GetInstance().EnumerateDevices():
    row={'model':d.GetModelName(),'serial':d.GetSerialNumber(),'device_class':d.GetDeviceClass(),'nodes':{}}
    c=pylon.InstantCamera(pylon.TlFactory.GetInstance().CreateDevice(d))
    try:
        c.Open(); nm=c.GetNodeMap()
        names=['DeviceModelName','DeviceSerialNumber','DeviceFirmwareVersion','DeviceVersion','Width','Height','WidthMax','HeightMax','OffsetX','OffsetY','PixelFormat','PixelSize','SensorBitDepth','TransferBitDepth','PayloadSize','AcquisitionMode','AcquisitionFrameRate','AcquisitionFrameRateEnable','ResultingFrameRate','AcquisitionResultingFrameRate','ExposureTime','ExposureAuto','ExposureMode','Gain','GainAuto','DeviceLinkThroughputLimit','DeviceLinkThroughputLimitMode','DeviceLinkCurrentThroughput','BslDeviceLinkCurrentThroughput','TriggerSelector','TriggerMode','TriggerSource','TriggerActivation','TriggerDelay','LineSelector','LineMode','LineSource','LineInverter','LineStatus','LineStatusAll','ChunkModeActive','ChunkSelector','ChunkEnable','Timestamp','TimestampLatchValue','GevTimestampTickFrequency','BslTimestampTickFrequency','DeviceSFNCVersionMajor','DeviceSFNCVersionMinor','DeviceSFNCVersionSubMinor']
        allnodes=nm.GetNodes()
        names += [n.GetNode().GetName() for n in allnodes if any(s in n.GetNode().GetName().lower() for s in ['timestamp','counter','chunk','throughput'])]
        for name in sorted(set(names)):
            try: n=nm.GetNode(name)
            except Exception: continue
            if n is None: continue
            item={'implemented':bool(genicam.IsImplemented(n)),'available':bool(genicam.IsAvailable(n)),'readable':bool(genicam.IsReadable(n)),'writable':bool(genicam.IsWritable(n))}
            if item['readable']:
                for method,label in [('ToString','value'),('GetMin','min'),('GetMax','max'),('GetInc','increment'),('GetUnit','unit'),('GetDescription','description')]:
                    try: item[label]=getattr(n.GetNode() if method=='GetDescription' else n,method)()
                    except Exception: pass
                try: item['enum_entries']=[{'symbol':e.GetSymbolic(),'available':bool(genicam.IsAvailable(e))} for e in n.GetEntries()]
                except Exception: pass
            row['nodes'][name]=item
        try: (out/f'camera-{d.GetSerialNumber()}.pfs').write_text(pylon.FeaturePersistence.SaveToString(nm),encoding='utf-8')
        except Exception as e: row['pfs_error']=str(e)
        row['stream_grabber']={}
        sm=c.GetStreamGrabberNodeMap()
        for name in ['MaxTransferSize','NumMaxQueuedUrbs','MaxBufferSize','MaxNumBuffer','Statistic_Total_Buffer_Count','Statistic_Failed_Buffer_Count','Statistic_Last_Failed_Buffer_Status','TransferLoopThreadPriority']:
            try:
                n=sm.GetNode(name)
                if n is not None and genicam.IsReadable(n): row['stream_grabber'][name]=n.ToString()
            except Exception: pass
    except Exception as e: row['error']=str(e)
    finally:
        if c.IsOpen(): c.Close()
    rows.append(row)
result={'captured_at':datetime.datetime.now().astimezone().isoformat(),'loaded_pylon_version':pylon.GetPylonVersionString(),'read_only':True,'cameras':rows}
(out/'camera-capabilities.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
for r in rows:
    print(json.dumps({'model':r['model'],'serial':r['serial'],'error':r.get('error'),'nodes':len(r['nodes']),'key_values':{k:v for k,v in r['nodes'].items() if k in ['Width','Height','AcquisitionFrameRate','AcquisitionResultingFrameRate','ResultingFrameRate','TimestampLatchValue','GevTimestampTickFrequency','BslTimestampTickFrequency','PayloadSize','ExposureTime','TriggerSource','LineSelector','ChunkSelector']}}))
