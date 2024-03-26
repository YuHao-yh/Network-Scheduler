import socket
import sys
import traceback
from threading import Thread
import client1
from PyQt5 import QtCore
from PyQt5.QtWidgets import QApplication, QDialog,  QMessageBox
import re
import pyperclip

def listen(window):
    while True:
        try:
            back_msg, addr = udp_sk.recvfrom(1024)
        except Exception:
            continue
        recv = back_msg.decode('utf-8')
        print(recv)
        if recv == 'isConnect':
            udp_sk.sendto("connect".encode('utf-8'), ip_port)
            continue
        window.recv = recv

class MainDialog1(QDialog):

    def __init__(self, parent=None):
        super(QDialog, self).__init__(parent)
        self.ui = client1.Ui_Dialog()
        self.ui.setupUi(self)
        # 定时发送
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.connect_test)
        self.timer.start(5000)
        # 接收信息
        self.recv = ''
        self.timer_message = QtCore.QTimer()
        self.timer_message.timeout.connect(self.showMessage)
        self.timer_message.start(1000)

    def connect_test(self):
        try:
            udp_sk.sendto("connect".encode('utf-8'), ip_port)
        except Exception:
            print(traceback.format_exc())

    def getInput(self):
        input_get = self.ui.lineEdit.text()
        return input_get

    def sendIntention(self):
        udp_sk.sendto(self.getInput().encode('utf-8'), ip_port)

    def showMessage(self):
        if not self.recv == '':
            recv = self.recv
            self.recv = ''
            address = re.search(r'address:(.*)', recv)
            self.setWindowFlag(QtCore.Qt.WindowStaysOnTopHint, True)
            self.setVisible(True)
            if address is not None:
                address = recv.replace("address:", '')
                txt = "拉流地址为：" + address + "\n"
                txt += "    点击\"Yes\"复制"
                message = QMessageBox.information(self, "消息", txt, QMessageBox.Yes | QMessageBox.No)
                if message == QMessageBox.Yes:
                    pyperclip.copy(address)
            else:
                QMessageBox.information(self, "消息", recv)
            self.setWindowFlag(QtCore.Qt.WindowStaysOnTopHint, False)
            self.setVisible(True)

if __name__ == '__main__':
    ip_port = ('192.168.1.12', 9554)  # 服务器的ip与端口
# 创建一个服务器的套接字,基于udp协议 type=socket.SOCK_DGRAM
    udp_sk = socket.socket(type=socket.SOCK_DGRAM)
    connectText = "connect"
    udp_sk.sendto(connectText.encode('utf-8'), ip_port)
    myapp1 = QApplication(sys.argv)
    myDlg1 = MainDialog1()
    myDlg1.show()
    thread2 = Thread(target=listen, args=(myDlg1,))
    thread2.daemon = True
    thread2.start()
    sys.exit(myapp1.exec_())
