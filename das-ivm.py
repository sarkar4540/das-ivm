import serial
import time
import requests
import subprocess
from mpu9250 import *

PORT = "/dev/pts/2"
DEPLOYED = False
BAUD = 115200
INIT_COMMANDS = ['AT E0', 'AT L0', 'AT H0', 'AT S0', 'AT IB 10']
INFO_COMMANDS = ['AT I', 'AT @1', 'AT @2', 'AT DP',
                 'AT RV', 'AT CS', 'AT KW', 'AT BD', 'AT PPS']
SUPPORTED_PIDS = []

start_time = time.time()

SERVER_ADDRESS = "http://10.21.112.135:3000"
process = None
if DEPLOYED:
    process = subprocess.Popen(
        "raspivid -t 0 -l -o tcp://0.0.0.0:3333".split(" "))

device_session = requests.get(
    SERVER_ADDRESS+"/device_session/PROTOTYPE_1").text


def command(Serial, Command):
    # Writes a command to the serial port and returns the response
    Command = Command.encode('ascii') + b'\r'
    Serial.write(Command)
    Response = ""
    ReadChar = 1
    while ReadChar != b'>' and ReadChar != b'' and ReadChar != 0:
        ReadChar = Serial.read()
        if ReadChar != b'>':
            Response += str(ReadChar, 'utf-8')
    Result = Response.strip()
    return Result


def pid_command(Serial, PID):
    Response = command(Serial, PID)
    if Response.replace(" ", "") == "NODATA":
        return None
    Result = []
    for line in Response.split("\r"):
        Result.append(line[4:] if (line.startswith(
            "4"+PID[1:]) and len(line) > 4) else "00")
    return Result


with serial.Serial(PORT, BAUD) as ser:
    print(command(ser, "AT Z"))
    info_dict = dict()
    init_dict = dict()
    # running all info commands to identify the type of elm327 and can bus
    for cmd in INFO_COMMANDS:
        info_dict[cmd] = command(ser, cmd)

    print(info_dict)

    # running all init commands to speed up communications
    for cmd in INIT_COMMANDS:
        init_dict[cmd] = command(ser, cmd)

    print(init_dict)

    # running a conditional sequence of commands to know which PIDs are
    # supported
    for index in range(0, 255, 32):
        current_cmd = "01"+format(index, '0>2x').upper()
        response = command(ser, current_cmd).split('\r')
        print(current_cmd+" : "+str(response))
        response_ok = False
        scan_next = False
        for response_line in response:
            if response_line.startswith("41"+format(index, '0>2x').upper()):
                response_ok = True
                # converting hex-string to integer
                val = int(response_line[4:], 16)
                # val in binary
                print(format(val, '0>32b'))
                # checking each bit, and if any bit is 1, adding the
                # corresponding PID to supported pids
                for loc in range(1, 32):
                    if val & (1 << loc):
                        pid = "01"+format(index+32-loc, '0>2x').upper()
                        if pid not in SUPPORTED_PIDS:
                            pid_response = pid_command(ser, pid)
                            if pid_response is not None:
                                SUPPORTED_PIDS.append(pid)
                if (val & 1):
                    scan_next = True
        if not (response_ok or scan_next):
            break

    SUPPORTED_PIDS.sort()
    print(SUPPORTED_PIDS)
    running = True
    while running:
        data = ""
        for pid in SUPPORTED_PIDS:
            pid_response = pid_command(ser, pid)
            if pid_response is not None:
                data = data+"\n"+str(int(time.time()-start_time)) + \
                    ","+pid+","+",".join(pid_response)
        try:
            ax, ay, az, wx, wy, wz = mpu6050_conv()
            data = data+"\n"+str(int(time.time()-start_time)) + \
                ",AX,"+","+str(ax) + \
                +"\n"+str(int(time.time()-start_time)) + \
                ",AY,"+","+str(ay) + \
                +"\n"+str(int(time.time()-start_time)) + \
                ",AZ,"+","+str(az) + \
                +"\n"+str(int(time.time()-start_time)) + \
                ",WX,"+","+str(wx) + \
                +"\n"+str(int(time.time()-start_time)) + \
                ",WY,"+","+str(wy) + \
                +"\n"+str(int(time.time()-start_time)) + \
                ",WZ,"+","+str(wz)
            mx, my, mz = AK8963_conv()
            data = data+"\n"+str(int(time.time()-start_time)) + \
                ",MX,"+","+str(mx) + \
                +"\n"+str(int(time.time()-start_time)) + \
                ",MY,"+","+str(my) + \
                +"\n"+str(int(time.time()-start_time)) + \
                ",MZ,"+","+str(mz)
        except Exception as e:
            print(e)
        print(data)
        r = requests.post(SERVER_ADDRESS+"/data", data,
                          headers={"device_session": device_session})
        print(r.text)

if DEPLOYED and process is not None:
    process.kill()
