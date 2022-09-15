import socket, struct

RECEIVER_IP = "192.168.1.64"
RECEIVER_PORT = 4444

receiver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
receiver.bind((RECEIVER_IP, RECEIVER_PORT))

while True:
    print("####### Server is listening #######")
    data = receiver.recv(1024)
    d = struct.unpack_from("I",data,offset=4)
    c = struct.unpack_from("I",data,offset=16)
    s = struct.unpack_from("?",data,offset=13)
    print("(%s, %s, %s)" % (d[0],c[0],s[0]))
    