#   WD_TCP_Client.py
#   ใช้สำหรับเชื่อมต่อและสื่อสารกับ Server(Redpitaya)

import socket
import json
import struct

# PORT เริ่มต้นที่ใช้เปิด Socket
PORT_INIT = 5000

# Timeout 
TIMEOUT   = 15


# Gobal Variable
SOCKET_STATE  = False       # flag การเชื่อมต่อ (False ยังไม่เชื่อมต่อ, True เชื่อมต่ออยู่)
SOCKET_CLIENT = None        # Object ของ Socket ที่ใช้คุยกับ Server


def _close_socket():
    '''
    ปิด Socket ฝั่ง Client reset ค่าของตัวแปร กลับเป็นค่าเริ่มต้น 
    '''
    # ให้ function นี้เป็นจุสำหรับเปลี่ยนค่า Gobal variable
    global SOCKET_STATE, SOCKET_CLIENT

    if SOCKET_CLIENT is not None:
        try:
            SOCKET_CLIENT.close()
        except OSError:
            pass

    SOCKET_CLIENT = None
    SOCKET_STATE  = False


# =================================
# Connect
# =================================
# เปิด TCP Socket ฝั่ง Client แล้วเชื่อมต่อไปที่ Server (Redpitaya) ที่ PORT_INIT
def connect_server(host_name):
    '''
    เชื่อมต่อไปยัง Server ผ่าน TCP Socket
    Parameters:
        host_name (str): IP address หรือ hostname ของ Server ที่ต้องการเชื่อมต่อ

    Returns:
        bool:   True ถ้าเชื่อมต่อสำเร็จ    
        
                False ถ้าเชื่อมต่อไม่สำเร็จ หรือมีการเชื่อมต่ออยู่แล้ว
    '''
    global SOCKET_STATE, SOCKET_CLIENT

    # ถ้าเชื่อมต่ออยู่ จะต้องไม่เชื่อมต่อซ้า
    if SOCKET_STATE == True:
        return False

    # เชี่อมต่อไปที่ Server ถ้าเชื่อมสำเร็จจะเก็บ SOCKET_CLIENT, เปลี่ยน flag SOCKET_STATE เป็น TRUE
    try:
        SOCKET_CLIENT = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        # SOCKET_CLIENT.settimeout(TIMEOUT)
        SOCKET_CLIENT.connect((host_name, PORT_INIT))
        SOCKET_CLIENT.settimeout(TIMEOUT)
        

        SOCKET_STATE = True

        return True

    except OSError:
        # reset gobal variable ไปที่ค่าเริ่มต้น
        _close_socket()

        return False


# =================================
# Disconnect
# =================================
#
# ตัดการเชื่อมต่อกับ Server ปิด Socket และ reset Gobal Variable กลับเป็นค่าเริ่มต้น
# ผ่าน _close_socket() เพื่อให้พร้อมเชื่อมต่อใหม่ในครั้งถัดไป
#
def disconnect_server():
    '''
    ตัดการเชื่อมต่อกับ Server และปิด Socket
    
    Returns:
        bool:   True ถ้า "ก่อนหน้า" มีการเชื่อมต่ออยู่
        
                False ถ้า "ก่อนหน้า" ยังไม่ได้มีการเชื่อมต่อ
    '''
    
    was_connected = SOCKET_STATE
    # reset gobal variable ไปที่ค่าเริ่มต้น
    _close_socket()

    return was_connected


# =================================
# Send
# =================================
#
# ส่งข้อมูลแบบ length-prefixed framing:
#   [4 byte] = ความยาวของ payload (unsigned int, big-endian ผ่าน struct "!I")
#   [payload] = ข้อมูลจริง (dict -> JSON -> utf-8 bytes)
# ใช้ sendall() เพื่อให้แน่ใจว่าข้อมูลถูกส่งครบทุก byte
#
def send_to_server(message):
    '''
    ส่งคำสั่งไปที่ Server ที่เชื่อมต่ออยู่โดยจะส่ง 4 byte แรกเป็นความยาวของข้อมูลแล้ว
    byte ต่อจากนั้นจะเป็นข้อมูลจริง
 
    Parameters:
        message (dict): ข้อมูลที่ต้องการส่งไปที่ Server (จะถูกแปลงเป็น JSON)
                        ต้องเป็นข้อมูลที่ json.dumps รองรับ

    Returns:
        bool:   True ถ้าส่งข้อมูลสำเร็จ
        
                False ถ้าไม่ได้เชื่อมต่ออยู่ หรือส่งข้อมูลผ่าน Socket ไม่สำเร็จ
    '''
    
    # ถ้าไม่ได้เชื่อมต่อ ก็จะส่งไม่ได้
    if SOCKET_STATE == False:
        return False

    try:
        data_send = json.dumps(message).encode("utf-8")

        # Header 4 Bytes เก็บขนาดของ payload
        header = struct.pack("!I", len(data_send))
        # ส่งข้อมูลแบบ [len data] [data]
        SOCKET_CLIENT.sendall(header + data_send)

        return True

    except OSError:
        # reset gobal variable ไปที่ค่าเริ่มต้น
        _close_socket()

        return False


# =================================
# Receive
# =================================
#
# รับข้อมูลด้วย framing แบบเดียวกับฝั่ง Send:
#   1) อ่าน header 4 byte ก่อน -> unpack เป็นขนาดของ payload
#   2) อ่าน payload ต่อจนครบตามขนาดนั้น
# recv() อาจได้ข้อมูลมาไม่ครบในครั้งเดียว จึงต้องวนรับใน recv_all()
# จนกว่าจะครบ หรือเจอ b"" (server ปิด connection)
#
def recv_all(size):
    '''
    รับข้อมูลจาก Socket วนจนกว่าจะครบตามขนาดที่ต้องการ
 
    Parameters:
        size (int): จำนวน byte ที่ต้องการรับให้ครบ
 
    Returns:
        bytes: ข้อมูลที่รับมาครบตามขนาดที่ต้องการ
        
        None:  ถ้า server ปิด connection ก่อนรับครบ
    '''
    data = b""
    # วน loop รับข้อมูล
    while len(data) < size:
        packet = SOCKET_CLIENT.recv(size - len(data))

        # ได้ b"" แปลว่า server ปิด socket กลางทาง -> เลิกรอ ไม่วนต่อ
        if not packet:
            return None

        data += packet

    return data


def receive_from_server():
    '''
    รับข้อมูลมาจาก Server ที่เชื่อมต่ออยู่
 
    Returns:
        dict: ข้อมูลที่ได้รับจาก Server (แปลงจาก JSON แล้ว) ถ้ารับสำเร็จ
              โดยปกติเป็น dict แต่จริง ๆ จะเป็นชนิดตาม JSON ที่ Server ส่งมา
              (list, str, int, bool, None ก็เป็นไปได้)
              
        None: ถ้ายังไม่เชื่อมต่อ, connection หลุดระหว่างรับข้อมูล,
              หรือ payload parse เป็น JSON ไม่ได้ (json.JSONDecodeError)
    '''
    
    # ยังไม่เชื่อมต่อ
    if SOCKET_STATE == False:
        return None

    try:
        # Header
        header = recv_all(4)

        if header is None:
            # reset gobal variable ไปที่ค่าเริ่มต้น
            _close_socket()
            return None

        # Header -> ขนาดของข้อมูลจริง
        payload_size = struct.unpack("!I", header)[0]

        payload = recv_all(payload_size)
        
        # ckeck ว่า server หลุดไปรึยัง
        if payload is None:
            # reset gobal variable ไปที่ค่าเริ่มต้น
            _close_socket()
            return None

        # Bytes -> Python object (ปกติเป็น dict ตาม protocol ที่ตกลงกับ Server)
        return json.loads(payload.decode("utf-8"))

    except (OSError, json.JSONDecodeError, struct.error):
        
        # reset gobal variable ไปที่ค่าเริ่มต้น
        _close_socket()
        return None


