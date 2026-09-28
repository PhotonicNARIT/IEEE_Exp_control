#   RP_TCP_Server.py
#   เป็นจุดเริ่มต้นของโปรแกรมฝั่ง Red Pitaya (RP)
#   เปิด TCP Server รอรับคำสั่งจาก client แล้วส่งงานต่อให้ RP_Command_handler
#
#   โปรโตคอลรับส่งข้อมูล (length-prefixed framing):
#       [4 byte] = ความยาว payload (unsigned int, big-endian ผ่าน struct "!I")
#       [payload] = ข้อมูลจริง (dict -> JSON -> utf-8 bytes)
#
#   flow: create_server -> รอ client -> วนรับคำสั่ง -> process_callback -> ตอบกลับ
#         -> เจอ disconnect/poweroff ค่อยปิด socket / ปิด server

import socket
import json
from RP_Command_handler import process_callback, board_poweroff
# import rp                 # ไลบรารีควบคุมฮาร์ดแวร์ Red Pitaya
import struct             


# =================================
# Server setup
# =================================

def create_server(host, port):
    '''
    สร้างและเปิด TCP server socket (ตั้ง SO_REUSEADDR กัน bind ไม่ได้ตอนรีสตาร์ท)

    Parameters:
        host (str): IP ที่จะ bind เช่น "0.0.0.0" (ทุก interface)
        port (int): พอร์ตที่รอรับการเชื่อมต่อ

    Returns:
    
        socket.socket: server socket ที่ listen แล้ว พร้อม accept
    '''
    # สร้าง Server 
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((host, port))

    server.listen()
    return server


def accept_client(server):
    '''
    บล็อกรอจนกว่าจะมี client เชื่อมต่อเข้ามา

    Returns:
        (socket.socket, tuple): socket ของ client และ address ของ client
    '''
    socket_for_client, addr_client = server.accept()
    return socket_for_client, addr_client


def disconnect_client(socket_for_client):
    '''
    ปิด socket ของ client 1 ราย
    '''
    socket_for_client.close()


def stop_server(server):
    '''
    ปิด socket ของตัว server
    '''
    server.close()


# =================================
# Send
# =================================
# ส่งข้อมูลแบบ [len data (4 byte)][data]: header 4 byte (ขนาด payload) ตามด้วย payload
#
def send_to_client(socket_for_client, reply_data):
    '''
    ส่ง reply กลับไปหา client (dict -> JSON -> bytes -> header + payload)

    Parameters:
        socket_for_client (socket.socket): socket ของ client ปลายทาง
        
        reply_data (dict): ข้อมูลที่จะตอบกลับ
    '''
    payload = json.dumps(reply_data).encode("utf-8")

    # "!I" = big-endian unsigned int (4 bytes) เก็บความยาวของ payload
    header = struct.pack("!I", len(payload))

    socket_for_client.sendall(header)
    socket_for_client.sendall(payload)


# =================================
# Receive
# =================================
# รับข้อมูลด้วย framing แบบเดียวกับฝั่ง Send:
#   1) อ่าน header 4 byte -> unpack เป็นขนาดของ payload
#   2) อ่าน payload ต่อจนครบตามขนาดนั้น
#
def receive_from_client(socket_for_client):
    '''
    รับข้อมูล 1 ก้อนจาก client แล้วแปลงกลับเป็น dict

    Returns:
        dict: คำสั่งจาก client (แปลงจาก JSON แล้ว) ถ้ารับสำเร็จ
        None: ถ้า client ตัดการเชื่อมต่อ หรือเจอ ConnectionResetError
    '''
    try:

        # รับ Header 4 Bytes
        header = recv_all(socket_for_client, 4)

        if header is None:
            return None

        # Header -> ขนาดของ payload ที่ต้องรับต่อ
        payload_size = struct.unpack("!I", header)[0]

        payload = recv_all(socket_for_client, payload_size)

        if payload is None:
            return None

        # Bytes -> Dict
        input_parameter_data = json.loads(payload.decode("utf-8"))

        return input_parameter_data

    except ConnectionResetError:
        return None


def recv_all(socket_for_client, size):
    '''
    รับข้อมูลจาก socket วนจนกว่าจะครบตามขนาดที่ต้องการ

    Parameters:
        size (int): จำนวน byte ที่ต้องการรับให้ครบ

    Returns:
        bytes: ข้อมูลครบตามขนาดที่ต้องการ
        None:  ถ้า client ปิด connection ก่อนรับครบ (recv ได้ b"")
    '''
    data = b""
    # วน loop รับข้อมูล
    while len(data) < size:
        packet = socket_for_client.recv(size - len(data))

        # ได้ b"" แปลว่าอีกฝั่งปิด socket กลางทาง -> เลิกรอ
        if not packet:
            return None

        data += packet

    return data


# =================================
# MAIN
# =================================
HOST = "0.0.0.0"   # รับการเชื่อมต่อจากทุก network interface
PORT = 5000

# สร้าง Server
server = create_server(HOST, PORT)
print(f"Server Start {HOST}:{PORT}")

# # เตรียมฮาร์ดแวร์ Red Pitaya ให้อยู่ในสถานะเริ่มต้น
# rp.rp_Init()          # คือฟังก์ชันที่ใช้ เปิดการเชื่อมต่อกับฮาร์ดแวร์ Red Pitaya
# rp.rp_ApinReset()     # reset ขา analog
# rp.rp_DpinReset()     # reset ขา digital

server_run = True

# ลูปนอก: รับ client ทีละราย
while server_run:

    print("Waiting client...")

    socket_for_client, addr_client = accept_client(server)

    print("Client connected:", addr_client)

    client_connected = True

    # ลูปใน: วนรับ-ตอบคำสั่งของ client รายนี้
    while client_connected:
        input_parameter_data = receive_from_client(socket_for_client)

        # None = client หลุด/ตัดการเชื่อมต่อ -> ออกไปรอ client รายใหม่
        if input_parameter_data is None:
            print("Client disconnected")
            disconnect_client(socket_for_client)
            client_connected = False
            continue

        # reply_data     = ข้อมูลที่จะตอบกลับ client
        # control_server = คำสั่งควบคุม server ("continue" / "disconnect" / "poweroff")
        reply_data, control_server = process_callback(input_parameter_data)

        if reply_data:
            send_to_client(socket_for_client, reply_data)

        # Control Server: ตัดสินใจตามผลลัพธ์จาก handler
        if control_server == "disconnect":
            disconnect_client(socket_for_client)
            client_connected = False

        elif control_server == "poweroff":
            disconnect_client(socket_for_client)
            client_connected = False
            server_run = False        # ออกจากลูปนอกด้วย -> เตรียมปิดเครื่อง

stop_server(server)

# สั่งปิดบอร์ดจริง (เรียก command poweroff ของระบบ)
board_poweroff()
