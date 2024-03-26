import sys
import os
import re
import json
import time
import math
import traceback

import ui
import message

import asyncio
import websockets
import requests
import socket
import subprocess
import paramiko
from threading import Thread

from PyQt5.Qt import *
from PyQt5 import QtCore
from PyQt5.QtWidgets import QApplication, QDialog, QTableWidgetItem, QMessageBox
from PyQt5.QtChart import QChart, QValueAxis, QLineSeries

import yaml



    
#部署yaml
def applyYaml(file):
    try:
        subprocess.run(['kubectl', 'apply', '-f', file], check=True)
    except Exception as r:
        print(r)
        
        
def deleteYaml(file):
    try:
        subprocess.run(['kubectl', 'delete', '-f', file], check=True)
    except Exception as r:
        print(r)

def convert_bps(bps):
    if bps>10**3 and bps<10**6+1:
        return bps/10**3,'Kbps'
    elif bps>10**6:
        return bps/10**6,'Mbps'
    else:
        return bps,'bps'

class MainDialog(QDialog):
    def __init__(self, parent=None):

        super(QDialog, self).__init__(parent)
        self.ui = ui.Ui_Form()    # 传入ui界面
        self.message = newWindow(self)  #弹窗实例化
        self.ui.setupUi(self)       # 初始化ui

        self.ui.tableWidget_access.setColumnWidth(2, 150)   #设置imsi列宽度

        self.ui.graphicsView_plot.hide()    # 隐藏实时曲线窗口
        self.ui.tableWidget.hide()
        self.ui.pushButton_quit.hide()
        self.ui.pushButton_RB.hide()
        self.ui.pushButton_bitrate.hide()
        

        # 加载Qchart波形界面
        self.plot_qchart = QChartViewPlot()
        self.ui.graphicsView_plot.setChart(self.plot_qchart)
        self.ui.graphicsView_plot.setRenderHint(QPainter.Antialiasing)  # 抗锯齿
        # self.ui.graphicsView_plot.setRubberBand(QChartView.RectangleRubberBand)     # 开启缩放

        #创建拓扑图
        width = self.ui.graphicsView_net.width()
        height = self.ui.graphicsView_net.height()
        self.topology = networkTopology()
        self.topology.setSize(width, height)    #设置画布大小
        self.ui.graphicsView_net.setScene(self.topology)    #添加画布
        self.ui.graphicsView_net.setAlignment(Qt.AlignLeft | Qt.AlignTop)   #固定画布与窗口的相对位置
        
        #定义计时器
        self.timer=QtCore.QTimer(self)
        self.timer.timeout.connect(self.update)
        self.timer.start(1000)
        #与update线程交换数据
        self.update_flag = False
        self.update_vonnect_flag = False
        #表格
        self.nodes_list = []
        self.pods_list = []
        self.access_list = [] 
        #拓扑图
        self.node_relation = []
        self.node_state = []
        #部署
        self.task={'gnb1':'close',
                   'gnb2':'close',
                   'mme':'close',
                   'ftp':'close',
                   'ai0':'close',
                   'ai1':'close'}
        self.init = False
        #任务性能指标
        self.task_show = []
        self.ai_delay_memory = [-1,-1,-1]
        #record
        self.record_contents = []
        #客户端请求
        self.request = ''

    def setSocket(self, Socket):
        self.message.Socket = Socket
        
    # 更新表格
    def updateTable(self, table, datas):
        if not table.rowCount() == len(datas):
            table.setRowCount(len(datas))
        for row in range(len(datas)):
            for col in range(len(datas[row])):
                table.setItem(row, col, QTableWidgetItem(str(datas[row][col])))     #更改内容

    #更新节点列表
    def updateNodeTable(self, datas):
        if self.ui.graphicsView_plot.isVisible() and self.eventFrom == 'tableWidget_node':
            for data in datas:
                if data[0] == self.row:
                    self.plot_qchart.handle_update(data[self.col])
                    return
            self.hidePlot()
        else:
            self.updateTable(self.ui.tableWidget_node, datas)

    #更新用户列表
    def updateAccessTable(self, datas):
        if self.ui.graphicsView_plot.isVisible() and self.eventFrom == 'tableWidget_access':
            for data in datas:
                if data[2] == self.row:
                    if self.col == 5:
                        self.plot_qchart.handle_update(data[self.col])
                    else:
                        self.plot_qchart.handle_update(data[self.col]/10**3,True)
                    return
            self.hidePlot()
        else:
            datas_str = []
            for i in range(len(datas)):
                datas_str.append(datas[i].copy())
                num_u,bps_u = convert_bps(datas[i][3])
                num_d,bps_d = convert_bps(datas[i][4])
                #data=str(datas[i])
                #print(data)
                datas_str[i][3] = str(num_u)+bps_u
                datas_str[i][4] = str(num_d)+bps_d
            self.updateTable(self.ui.tableWidget_access, datas_str)
    #更新pods列表
    def updatePodsTable(self, datas):
        datas_select = []
        #print(datas)
        if self.ui.tableWidget.isVisible():
            for pod in datas:
                #print(pod['nodeName'])
                if pod['nodeName'] == self.row:
                    datas_select.append([pod['name'],pod['cpu'],pod['memory']])        
            self.updateTable(self.ui.tableWidget, datas_select)

    #展示动态图
    def showPlot(self, row):
        self.ui.tableWidget.hide()
        self.eventFrom = self.sender().objectName() #获取事件触发来源
        plot = self.ui.graphicsView_plot
        if plot.isHidden():
            plot.show()
            self.col = 3
            self.ui.pushButton_quit.show()
            if self.eventFrom == 'tableWidget_node':
                title = self.ui.tableWidget_node.item(row, 0).text()
                self.plot_qchart.setText([str(title), '时间', 'CPU利用率', 'CPU利用率'])
            elif self.eventFrom == 'tableWidget_access':
                #self.ui.pushButton_RB.show()
                self.ui.pushButton_bitrate.show()
                title = self.ui.tableWidget_access.item(row, 2).text()
                self.plot_qchart.setText([str(title), '时间', '上行速率Kbps', '上行速率Kbps'])
            self.row = title
            self.plot_qchart.reset()
    def bitrate(self):
        title = self.row
        if self.col == 3:
            self.col =4
            self.plot_qchart.setText([str(title), '时间', '下行速率Kbps', '下行速率Kbps'])
            self.plot_qchart.reset()
        else:
            self.col =3
            self.plot_qchart.setText([str(title), '时间', '上行速率Kbps', '上行速率Kbps'])
            self.plot_qchart.reset()
    def RB(self):
        self.col = 5
        title = self.ui.tableWidget_access.item(self.row, 2).text()
        self.plot_qchart.setText([str(title), '时间', 'RB利用率', 'RB利用率'])
        self.plot_qchart.reset()

    def hidePlot(self):
        self.ui.graphicsView_plot.hide()
        self.ui.pushButton_quit.hide()
        if self.eventFrom == 'tableWidget_access':
            self.ui.pushButton_RB.hide()
            self.ui.pushButton_bitrate.hide()

    #展示pod信息
    def showPods(self,row):
        #print(self.pods_list)
        title = self.ui.tableWidget_node.item(row, 0).text()
        pod_show = self.ui.tableWidget
        if pod_show.isHidden():
            pod_show.show()
            self.row = title
        elif title == self.row:
            pod_show.hide()
        else:
            self.row = title
            
    #  拓扑图
    def createTopo(self, nodes):
        topo = self.topology
        topo.initCenter()
        layer = 1
        layer_max = 0
        node_list = []
        node_dic = {'center': {'layer': 0, 'child': []}}
        for node in nodes:
            if node[1] == '':
                layer = 1
                node_list.append(node[0])
                node_dic['center']['child'].append(node[0])
                node_dic[str(node[0])] = {'layer': layer, 'child': []}
            elif node[0] in node_list:
                if not node[1] in node_dic[str(node[0])]['child']:
                    node_dic[str(node[0])]['child'].append(node[1])
                if not node[1] in node_list:
                    node_list.append(node[1])
                    layer = node_dic[str(node[0])]['layer'] + 1
                    node_dic[str(node[1])] = {'layer': layer, 'child': []}
            elif node[1] in node_list:
                node_list.append(node[0])
                layer = node_dic[str(node[1])]['layer'] + 1
                node_dic[str(node[1])]['child'].append(node[0])
                node_dic[str(node[0])] = {'layer': layer, 'child': []}
            else:
                layer = 1
                node_list.append(node[0])
                node_dic['center']['child'].append(node[0])
                node_dic[str(node[0])] = {'layer': layer, 'child': []}
                node_list.append(node[1])
                node_dic['center']['child'].append(node[1])
                node_dic[str(node[1])] = {'layer': layer, 'child': []}
            if layer > layer_max:
                layer_max = layer
        #print(node_dic)
        distance = topo.height / (layer_max * 2 + 2)
        #画交换机
        centerChildNode = node_dic['center']['child']
        num = len(centerChildNode)
        offest = math.pi/4
        for n in range(num):
            angle_node = 2 * math.pi * n / num
            angle_node += offest
            x = math.cos(angle_node) * (distance + 1) + topo.width / 2
            y = -math.sin(angle_node) * (distance + 1) + topo.height / 2
            topo.updataNode(centerChildNode[n], [x, y])
            topo.updataLine(['center', centerChildNode[n]])
        # 画连线
        for node in nodes:
            if not node[1] == '':
                topo.updataLine(node)
                
    # 切换AI业务
    def changeAi(self):
        self.record_contents.append('触发Ai切换')
        self.task['ai1'] = 'close_now'
        self.task['ai0'] = 'start'
        while True:
            if self.task['ai0'] == 'Running':
                delay = self.ai_delay_memory
                #print("++"*15,delay,"++"*15)
                #print(-1 in delay)
                if delay[0] == delay[1] or delay[1] == delay[2] or -1 in delay:
                    continue
                self.record_contents.append('Ai切换完成')
                recv = 'address:'+self.rtmp_ai2
                if self.message.isReqAi:
                    while True:
                        if self.update_vonnect_flag:
                            self.update_vonnect_flag = False
                            print("connect")
                            if self.message.Socket.isConnect():
                                break
                    print('send')
                    print(recv)
                    if not recv == '':
                        self.message.Socket.sendMsg(recv)
                    print('send')
                break
    # 定时更新函数
    def update(self):
        self.update_flag = True
        self.update_vonnect_flag = True
        #节点
        self.updateNodeTable(self.nodes_list)
        #pods
        self.updatePodsTable(self.pods_list)
        self.message.pods = [pod['name'] for pod in self.pods_list]
        #用户
        self.updateAccessTable(self.access_list)
        
        #拓扑图
        node_relation = self.node_relation
        if not node_relation == []:
    	    self.createTopo(node_relation)
        for node in self.node_state:
    	    self.topology.changeState(node[0],node[1])
    	
    	#业务指标
        self.updateTable(self.ui.tableWidget_access_2,self.task_show)
        self.message.ai_delay_memory = self.ai_delay_memory
        
        #客户端请求
        if not self.request == '':
            self.message.showMessage(self.request)
            self.request = ''
        
        #更新record
        if len(self.record_contents)>0:
            for content in self.record_contents:
                self.addRecord(content)
            self.record_contents = []
    	
    # 配置部分
    def init(self):
        print("init")
        self.ui.textEdit_settingRecord.clear()
        self.init = True
        #self.nodes_list = []
        self.access_list = []
        self.task_show = []
        self.message.isReqAi = False
        
    def addRecord(self, content):
        record = "="*5 + time.strftime('%Y-%m-%d %H:%M:%S') + "="*5 + "\n"
        record += content
        self.ui.textEdit_settingRecord.append(record)
        self.ui.textEdit_settingRecord.moveCursor(QTextCursor.End)

    def setting(self):
        text = self.ui.comboBox_1.currentText()
        
        self.addRecord("部署业务：{}".format(text))
        if text == "gnb 1(40M)":
            self.task['gnb1'] = 'start'
            
        elif text == "gnb 2(100M)":
            self.task['gnb2'] = 'start'
            
        elif text == "核心网":
            self.task['mme'] = 'start'
            
        elif text == "FTP业务":
            self.task['ftp'] = 'start'
            
        elif text == "目标识别业务":
            self.task['ai1'] = 'start'
            
    def record(self, content):
        print(content)
        self.record_contents.append(content)
        



# 新窗口
class newWindow(QDialog):
    def __init__(self, main):
        super().__init__()
        #self.setWindowTitle('新窗口')
        #self.resize(280, 230)
        self.main = main
        self.message = message.Ui_Dialog()  # 传入ui界面
        self.message.setupUi(self)
        self.setWindowFlag(QtCore.Qt.WindowStaysOnTopHint)
        self.show()
        self.hide()
        # 数据
        self.ai_delay_memory = [-1,-1,-1]
        self.pods = []
        # 请求
        self.request = ''
        #记录弹窗
        self.message_num = 0
        #记录请求
        self.isReqAi = False
        
    # 确认请求对话框
    def showMessage(self, request):
        self.show()
        self.message.textEdit.append(request)
        self.message.pushButton_accept.setFocus()
        self.message.pushButton_accept.setText("转译")
        self.main.addRecord('用户请求：'+str(request))
        self.request = request

    def recv_task(self,task,recv = ''):
        self.main.task[task] = 'start'
        while not self.main.task[task] == 'Running':
            time.sleep(1)
        
        if task == 'ftp':
            recv = "ftp业务已开启"
        elif task == 'gnb2':
            recv = "ftp速率增强完成"
        elif task == 'ai0':
            recv = 'address:'+self.main.rtmp_ai2
        elif task == 'ai1':
            recv = 'address:'+self.main.rtmp_ai1
            while True:
                delay = self.ai_delay_memory
                if not delay[0] == delay[1] and not delay[1] == delay[2] and not delay[-1] == -1:
                    if 'enb-test' in self.pods and 'yolo1-test' in self.pods:
                        break
        print(recv)
        while True:
            if self.main.update_vonnect_flag:
                self.main.update_vonnect_flag = False
                print("connect")
                if self.Socket.isConnect():
                    break
        print('send')
        print(recv)
        if not recv == '':
            self.Socket.sendMsg(recv)
        print('send')

    def accept(self):
        if self.message_num == 0:
            self.main.addRecord('同意转译')
            #self.message.textEdit.clear()
            self.message.textEdit.append("是否部署？")
            self.message.pushButton_accept.setText("部署")
            self.message_num = 1
        elif self.message_num == 1:
            #转译模块
            recv = ''
            task = ''
            #部署ftp;提升ftp速率
            if 'ftp' in self.request or 'FTP' in self.request:
                #提升ftp速率
                if '提升' in self.request:
                    #recv = 'gnb2'
                    task = 'gnb2'
                #部署ftp
                else:
                    #recv = 'ftp'
                    task = 'ftp'
                    
            #切换基站
            result = re.search(r'(\d+)(.*)[b|B][p|P][s|S]',self.request)
            if not result is None:
                rate = int(result.group(1))
                if self.main.task['gnb2'] == 'Running':
                    prb = 272
                else:
                    prb = 106
                rate_gnb = round(10**(-6)*8*(948/1024)*30*10**(3)*prb*12*(1-0.08),3)
                print(rate_gnb)
                if rate > rate_gnb:
                    self.main.task['gnb2'] = 'start'
                    prb = 272
                    rate_gnb = round(10**(-6)*8*(948/1024)*30*10**(3)*prb*12*(1-0.08),3)
                    recv = '切换100M基站，理论最大速率：'+str(rate_gnb)+'Mbps'
                else:
                    recv = '当前运行40M基站，理论最大速率：'+str(rate_gnb)+'Mbps'
            #部署目标识别
            if '目标识别' in self.request:
                self.isReqAi = True
                if self.main.task['ai0'] == 'Running':
                    task = 'ai0'
                elif self.main.task['ai1'] == 'Running':
                    task = 'ai1'
                else:
                    task = 'ai1'
                
            if not task == '':
                Thread(target=self.recv_task, args=(task,recv,)).start()
            self.message_num = 0
            self.message.textEdit.clear()
            self.hide()

    def reject(self):
        if self.message_num == 0:
            self.main.addRecord('拒绝转译')
            self.Socket.sendMsg("拒绝转译")
        elif self.message_num == 1:
            self.main.addRecord('拒绝部署')
            self.Socket.sendMsg("拒绝部署")
        self.message_num = 0
        self.message.textEdit.clear()
        self.hide()
# 波形显示
class QChartViewPlot(QChart):
    # 波形
    def __init__(self, parent=None):
        super(QChartViewPlot, self).__init__(parent)
        self.window = parent
        self.xRange = 60
        self.isLayout()
        self.seriesList = []
        self.legend().show()
        self.setTitleFont(QFont('SimSun', 20))
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.setMargins(QMargins(0, 0, 0, 0))

        self.axisX = QValueAxis()
        self.axisX.setRange(0, self.xRange)
        self.addAxis(self.axisX, Qt.AlignBottom)    # 与底部对齐
        # self.setAxisX(self.axisX, series)
        self.y_min = 0
        self.y_max = 100
        self.axisY = QValueAxis()
        self.axisY.setRange(self.y_min, self.y_max)
        self.addAxis(self.axisY, Qt.AlignLeft)
        # self.setAxisY(self.axisY, series)

        self.series = QLineSeries()
        for i in range(self.xRange):
            self.series.append(i, 0)
        self.series.setUseOpenGL(False)
        self.addSeries(self.series)
        self.series.attachAxis(self.axisX)
        self.series.attachAxis(self.axisY)
        #self.legend().markers()[0].setVisible(False)

        # 设置坐标轴上的格点
        self.axisX.setTickCount(13)  # 平均分的刻度分隔
        self.axisY.setTickCount(11)
        # 设置网格显示，并设为灰色
        self.axisY.setGridLineVisible(True)
        self.axisY.setGridLineColor(Qt.blue)
        self.axisX.setGridLineVisible(True)
        self.axisX.setGridLineColor(Qt.blue)
        self.axisX.setReverse(True)

    def setText(self, text):
        # 设置坐标轴名称
        self.setTitle(text[0])
        self.axisX.setTitleText(text[1])
        self.axisY.setTitleText(text[2])
        self.series.setName(text[3])

    def reset(self):
        #print('reset')
        points = self.series.pointsVector()
        for i in range(self.xRange):
            points[i].setY(0)
        self.series.replace(points)

    def handle_update(self, ydata,resize = False):
        # 更新y值
        points = self.series.pointsVector()
        for i in range(1, self.xRange):
            points[self.xRange-i].setY(points[self.xRange-i-1].y())
        points[0].setY(ydata)
        y_max = max(points, key=lambda point: point.y()).y()
        y_min = min(points, key=lambda point: point.y()).y()
        if resize:
            self.axisY.setRange(y_min, y_max)
        else:
            self.axisY.setRange(self.y_min, self.y_max)
        self.series.replace(points)

# 画拓扑图
class networkTopology(QGraphicsScene):
    def __init__(self, parent=None):
        super(QGraphicsScene, self).__init__(parent)
        self.scene = parent
        self.width = 0
        self.height = 0
        self.lineColor_0 = Qt.red
        self.lineWidth_0 = 1
        self.lineColor_1 = Qt.blue
        self.lineWidth_1 = 3
        self.pos = {}
        self.line = {}
        self.point_item = {}
        self.line_item_0 = {}
        self.line_item_1 = {}
        self.r = 20

    #初始化交换机
    def initCenter(self):
        item = self.addRect(self.width/2, self.height/2, self.r, self.r, QPen(Qt.black), QBrush(Qt.blue))
        self.pos['center'] = [self.width/2, self.height/2]
        self.point_item['center'] = item
        text = self.addSimpleText('交换机')
        text_pos = QPointF(self.width/2, self.height/2 + self.r)
        text.setPos(text_pos)

    def setSize(self, width, height):
        self.width = width - 10
        self.height = height - 10
        self.setSceneRect(0, 0, self.width, self.height)

    def updataNode(self, node, pos):
        if node in self.pos.keys():
            return
        #print(node)
        item = self.addEllipse(pos[0], pos[1], self.r, self.r, QPen(Qt.black), QBrush(Qt.red))
        self.pos[str(node)] = [pos[0], pos[1]]
        self.point_item[str(node)] = item
        text = self.addSimpleText(str(node))
        text_pos = QPointF(pos[0], pos[1] + self.r)
        text.setPos(text_pos)
        # print(self.pos)

    def updataLine(self, node):
        line_pen_0 = QPen(self.lineColor_0)
        line_pen_0.setWidth(self.lineWidth_0)
        pos = [self.pos[str(node[0])], self.pos[str(node[1])]]
        item_0 = self.addLine(pos[0][0] + self.r / 2, pos[0][1] + self.r / 2, pos[1][0] + self.r / 2,
                              pos[1][1] + self.r / 2, line_pen_0)
        item_0.show()
        self.line[str(node[0]) + ',' + str(node[1])] = pos
        self.line_item_0[str(node[0]) + ',' + str(node[1])] = item_0

        line_pen_1 = QPen(self.lineColor_1)
        line_pen_1.setWidth(self.lineWidth_1)
        pos = [self.pos[str(node[0])], self.pos[str(node[1])]]
        item_1 = self.addLine(pos[0][0] + self.r / 2, pos[0][1] + self.r / 2, pos[1][0] + self.r / 2,
                            pos[1][1] + self.r / 2, line_pen_1)
        item_1.hide()
        self.line[str(node[0])+','+str(node[1])] = pos
        self.line_item_1[str(node[0])+','+str(node[1])] = item_1
        #print(self.line)

    def changeState(self, node, state):
        #print(node)
        node_point = self.point_item[str(node)]
        if state:
            node_point.setBrush(QBrush(Qt.green))
        else:
            node_point.setBrush(QBrush(Qt.red))
        for line in self.line.keys():
            if node in line:
                if state:
                    self.line_item_0[line].hide()
                    self.line_item_1[line].show()
                else:
                    self.line_item_0[line].show()
                    self.line_item_1[line].hide()

class update:
    def __init__(self):
        self.node_list = []
        self.topo = []
        self.change_enb = []
        self.change_ai = []
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.topoInit = False
        self.pods2task = {'enb-test':'gnb1',
                          'enb-test2':'gnb2',
                          'mme-ims-test':'mme',
                          'ftp-test':'ftp',
                          'yolo-test':'ai0',
                          'yolo1-test':'ai1'}
        self.task2pods = dict([(p,t) for (t,p) in self.pods2task.items()])
        self.task2yaml = {'gnb1':'enb.yaml',
                          'gnb2':'enb2.yaml',
                          'mme':'mme-ims.yaml',
                          'ftp':'ftp.yaml',
                          'ai0':'yolo0.yaml',
                          'ai1':'yolo1.yaml'}
        print(self.task2pods)
        self.task_name = {'gnb1':'gnb1',
                          'gnb2':'gnb2',
                          'mme':'核心网',
                          'ftp':'FTP传输',
                          'ai0':'目标识别',
                          'ai1':'目标识别'}
        # 建立SSH连接
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())


    def start_loop(self, window):
        self.window = window
        self.update_data()

    def update_data(self):
        run_n=0
        while self.window.isVisible():
            #事实刷新
            #初始化
            if self.window.init:
                self.window.init = False
                for task in self.window.task:
                    if not self.window.task[task] == 'close':
                        self.window.task[task] = 'close'
                pods = self.pods_status()
                for pod in pods:
                    Thread(target=deleteYaml, args=(self.task2yaml[self.pods2task[pod[0]]],)).start()
                self.window.record('初始化中···')
                self.window.access_list = []
                self.window.task_show = []
                self.window.pods_list = []
                self.change_enb = []
                self.change_ai = []
                self.window.message.isReqAi = False
                while True:
                    pods = self.pods_status()
                    print(pods)
                    if len(pods) == 0 or self.window.init:
                        break
                    time.sleep(1)
                self.window.access_list = []
                self.window.task_show = []
                self.window.pods_list = []
                self.change_enb = []
                self.change_ai = []
                self.window.message.isReqAi = False
                self.window.record('初始化完成')
            
            if not self.window.update_flag:
                continue
                
            #UI更新后获取
            run_n+=1
            print(run_n)
            print('',"="*30,'\n === ',time.strftime('%Y-%m-%d %H:%M:%S'),'  ===\n',"="*30)
            
            #获取pod运行情况
            pods = self.pods_status()
            
            #更改任务状态
            for pod in pods:
                if pod[1] == 'Running':
                    if self.window.task[self.pods2task[pod[0]]] == 'wait':
                        self.window.record(self.task_name[self.pods2task[pod[0]]]+'业务已开始运行')
                        self.window.task[self.pods2task[pod[0]]] = 'Running'     
            print(self.window.task)
            
            #部署/删除yaml
            for task in self.window.task:
                if self.window.task[task] == 'start':
                    self.window.task[task] = 'wait'
                    if task == 'ai1':
                        # 配置SSH连接参数
                        hostname = self.hostname_ai1
                        username = self.username_ai1
                        password = self.password_ai1
                    elif task == 'ai0':
                        # 配置SSH连接参数
                        hostname = self.hostname_ai2
                        username = self.username_ai2
                        password = self.password_ai2
                    if 'ai' in task:
                        # 建立SSH连接
                        self.client.connect(hostname=hostname, username=username, password=password)
                    #基站切换
                    if task =='gnb2' and self.window.task['gnb1'] == 'Running':
                        self.window.task['gnb1'] = 'changed'
                    elif task =='gnb1' and self.window.task['gnb2'] == 'Running':
                        self.window.task['gnb2'] = 'changed'
                    self.window.record(task+'开始部署')
                    Thread(target=applyYaml, args=(self.task2yaml[task],)).start()
                elif self.window.task[task] == 'close_now':
                    self.window.task[task] = 'close'
                    self.window.record(task+'已关闭')
                    Thread(target=deleteYaml, args=(self.task2yaml[task],)).start()
            
            # API合并
            # 获取节点信息
            datas = self.getNodeInformation()
            #print(datas)
            node = []
            node_list = []
            node_state = []
            self.node_information = {}
            for data in datas:
                node_list.append(data['name'])
                if data['name'] not in self.node_list:
                    self.node_list.append(data['name'])
                    #拓扑图绘制规则---临时
                    self.topo.append([data['name'],''])
                    ####################
                    self.topoInit = False
                if not 'cpu_rate' in data:data['cpu_rate']= 00
                #更新状态
                if self.topoInit:
                    if data['status']:
                        node_state.append([data['name'],1])
                    else:
                        node_state.append([data['name'],0])
                node.append([data['name'], data['ip'], data['cpuNum'], data['cpu_rate']])
                if not 'memory' in data.keys(): data['memory'] = 1
                self.node_information[data['name']] = {'cpuNum' : data['cpuNum'],'memoryAll' : data['memoryAll']}
            self.window.nodes_list = node
            if not self.topoInit:
            	self.window.node_relation = self.topo
            	self.topoInit = True
            
            if not node_state == []:
                self.window.node_state = node_state
             
            #获取pod信息
            try:
                self.window.pods_list = self.getPodsInformation()
            except Exception:
            	print(traceback.format_exc())
            	
            #获取用户信息
            datas = []
            if (self.window.task['gnb1'] == 'Running' or self.window.task['gnb2'] == 'Running') and self.window.task['mme'] == 'Running':
                datas_1 = []
                datas_2 = []
                if self.window.task['gnb1'] == 'Running' or self.window.task['gnb1'] == 'ready_close':
                    datas_1 = self.ue_get(1)
                if self.window.task['gnb2'] == 'Running':
                    datas_2 = self.ue_get(2)
                datas=datas_1.copy()
                datas.extend(datas_2)
                #print(datas)
                ue = []
                if len(datas) >0:
                    for data in datas:
                        if not 'enb' in data:data['enb']=0
                        if not 'ul_bitrate' in data:data['ul_bitrate']=0
                        if not 'dl_bitrate' in data:data['dl_bitrate']=0
                        ue.append([data['enb'], data['ran_ue_id'], data['imsi'], data['ul_bitrate'], data['dl_bitrate']])
                self.window.access_list = ue
            
            #切换基站
            #降低功率
            if self.window.task['gnb1'] == 'changed' and self.window.task['gnb2'] == 'Running':
                self.window.record('gnb2已运行')
                Thread(target=self.setDB, args=(-100,1,)).start()
                self.window.record('gnb1降低功率')
                self.window.task['gnb1'] = 'ready_close'
            elif self.window.task['gnb2'] == 'changed' and self.window.task['gnb1'] == 'Running':
                self.window.record('gnb1已运行')
                Thread(target=self.setDB, args=(-100,2,)).start()
                self.window.record('gnb2降低功率')
                self.window.task['gnb2'] = 'ready_close'
            #关闭基站
            elif self.window.task['gnb1'] == 'ready_close':
                print(len(datas_1))
                if len(datas_1) == 0:
                    self.window.task['gnb1'] = 'close_now'
            elif self.window.task['gnb2'] == 'ready_close':
                print(len(datas_1))
                if len(datas_2) == 0:
                    self.window.task['gnb2'] = 'close_now'
            
            #展示业务指标
            if self.window.task['ftp'] == 'Running' or self.window.task['ai0'] == 'Running' or self.window.task['ai1'] == 'Running':
                Thread(target=self.update_task, args=(datas,)).start()
           
            #其他信息
            datas = self.cpuinfo_get()
            #print(datas)
            #time.sleep(1)
            self.window.update_flag = False
            #print('*'*20,'end','*'*20,'\n\n')
        self.client.close()
        self.loop.stop()
    def pods_status(self):
        url = 'http://127.0.0.1:8080/api/v1/namespaces/default/pods'
        pods = json.loads(requests.get(url).text)
        pods_list=[]
        for pod in pods['items']:
            if not pod['metadata']['name'] in self.pods2task.keys():continue 
            pods_list.append([pod['metadata']['name'],pod['status']['phase']])
        return pods_list
        
    def getNodeInformation(self):
        print('\n','#'*10,'get node','#'*10)
        information = []
        
        url = 'http://127.0.0.1:8080/api/v1/nodes'
        page = requests.get(url)
        nodes = json.loads(page.text)
        
        for item in nodes['items']:
            tmp = {}
            tmp['name'] = item['metadata']['name']
            tmp['ip'] = item['status']['addresses'][0]['address']
            #print(tmp['ip'])
            #print(item)
            tmp['cpuNum'] = int(item['status']['capacity']['cpu'])
            tmp['memoryAll'] = int(item['status']['capacity']['memory'][0:-2])*10**(3)
            status = item['status']['conditions']
            for statu in status:
                if statu['type'] == 'Ready':
                    if statu['status'] == 'True':
                        tmp['status'] = True
                    else:
                        tmp['status'] = False
            information.append(tmp)
            
        try:
            url = 'http://127.0.0.1:8080/apis/metrics.k8s.io/v1beta1/nodes'
            page = requests.get(url)
            metrics_node = json.loads(page.text)
            
            #print(metrics_node)
            
            for item in metrics_node['items']:
                for node in information:
                    if node['name'] == item['metadata']['name']:
                        idx = information.index(node)
                        #print(item['usage']['cpu'])
                        #print(item['usage']['memory'])
                        s=item['usage']['cpu'][-1]
                        '''
                        if s == 'n':
                        	usage = int(item['usage']['cpu'][0:-1]) * 10 ** (-9)
                        elif s == 'u':
                        	usage = int(item['usage']['cpu'][0:-1]) * 10 ** (-6)
                        elif s == 'm':
                        	usage = int(item['usage']['cpu'][0:-1]) * 10 ** (-3)
                        '''
                        cpu = int(item['usage']['cpu'][0:-1]) * 10 ** (-9)
                        memory = int(item['usage']['memory'][0:-2])*10**(3)
                        
                        information[idx]['cpu'] = cpu
                        information[idx]['memory'] = memory
                        cpu_rate = cpu / int(node['cpuNum'])
                        information[idx]['cpu_rate'] = round((cpu_rate*100),5)
                        memory_rate = memory / int(node['memoryAll'])
                        information[idx]['memory_rate'] = round((memory_rate*100),5)
        except Exception:
            	print(traceback.format_exc())
        for node in information:
            print(node)
        return information

    def getPodsInformation(self):
        print('\n','#'*10,'get pods','#'*10)
        pods = {}
        url = 'http://127.0.0.1:8080/api/v1/pods'
        page = requests.get(url)
        data = json.loads(page.text)
        for item in data['items']:
            if item['metadata']['namespace'] == 'default':
                name = item['metadata']['name']
                nodeName = item['spec']['nodeName']
                pods[name] = nodeName
                try:
                    if not item['status']['containerStatuses'][0]['ready']:
                        print("-"*20)
                        print(name)
                        print(nodeName)
                        print(item['status']['containerStatuses'][0]['state']['waiting']['reason']+"\n"+"-"*20)
                except Exception:
                    print("-"*20)
                    continue
                
        pods_list = []
        url = 'http://127.0.0.1:8080/apis/metrics.k8s.io/v1beta1/namespaces/default/pods'
        page = requests.get(url)
        data = json.loads(page.text)
        for item in data['items']:
            name = item['metadata']['name']
            # 隐藏未启动pod
            hide = False
            for pod in self.window.task:
                if self.task2pods[pod] == name and self.window.task[pod] == 'close':
                    hide = True
            if hide:
                continue
            # 匹配数据
            nodeName = pods[name]
            if len(item['containers']) == 0:
                cpu = '0'
                memory = '0'
            else:
                cpu = item['containers'][0]['usage']['cpu']
                memory = item['containers'][0]['usage']['memory']
            if not cpu == '0':
                cpu_value = int(cpu[0:-1])* 10 ** (-9)
            else:
                cpu_value = int(cpu)
            
            if not memory == '0':
                memory_value = int(memory[0:-2])*10**(3)
            else:
                memory_value = int(memory)
            cpuNum_node = int(self.node_information[nodeName]['cpuNum'])
            memory_node = int(self.node_information[nodeName]['memoryAll'])
            pods_list.append({'name':name,
                              'nodeName':nodeName,
                              'cpu':round((cpu_value/cpuNum_node)*100,5),
                              'memory':round((memory_value/memory_node)*100,5)})
            #print(name)
            #print(nodeName)
            #print(int(cpu_value*10**(3)))
            #print(int(memory_value*10**(-6)))
        for pod in pods_list:
            print(pod)
        return pods_list
        
    async  def connectByWebsocket(self, url, data,recv=True):
        #print(url,data)
        try:
            async with websockets.connect(url, origin="Test") as websocket:
                recv = await websocket.recv()
                recv_json = json.loads(recv)
                if recv_json['message'] == 'ready':
                    data_str = json.dumps(data)
                    await websocket.send(data_str)
                    if recv:
                        recv = await websocket.recv()
                        recv_json = json.loads(recv)
                        #print(recv_json)
                        return  recv_json
        except Exception:
            print(traceback.format_exc())
            return []

    def ue_get(self,n):
        ue_data = []
        url = 'ws://' + self.addr_mme
        data_send = {"message": "ue_get", "stats": True}
        data_get = self.loop.run_until_complete(self.connectByWebsocket(url, data_send))
        if data_get == []:return []
        ue_list_1 = data_get['ue_list']
        enbIp=[self.addr_enb1,self.addr_enb2]
        url = 'ws://' + enbIp[n-1]
        data_send = {"message": "ue_get", "stats": True}
        data_get = self.loop.run_until_complete(self.connectByWebsocket(url, data_send))
        if data_get == []:return []
        ue_list_2 = data_get['ue_list']

        # 核心网
        for ue in ue_list_1:
            if not 'ran_ue_id' in ue:continue
            tmp = {}
            tmp['ran_ue_id'] = ue['ran_ue_id']
            tmp['imsi'] = ue['imsi']
            ue_data.append(tmp)
        #print("=============")
        #基站
        ue_data_2=[]
        for ue in ue_list_2:
            for ue_ in ue_data:
                if ue['ran_ue_id'] == ue_['ran_ue_id']:
                    idx = ue_data.index(ue_)
                    ue_data[idx]['enb'] = n
                    ue_data[idx]['dl_bitrate'] = ue['cells'][0]['dl_bitrate']
                    ue_data[idx]['ul_bitrate'] = ue['cells'][0]['ul_bitrate']
                    ue_data_2.append(ue_data[idx])
        #print("="*10,n,"="*10)
        #print(ue_data)
        #print(ue_data_2)
        return ue_data_2

    def resourceLocks_get(self):
        url = 'ws://'+self.addr_enb1
        data_send = {"message": "config_get", "stats": True}
        data_get = self.loop.run_until_complete(self.connectByWebsocket(url, data_send))
        dataReturn = {}
        n_rb_dl = data_get['nr_cells']['1']['n_rb_dl']
        n_rb_ul = data_get['nr_cells']['1']['n_rb_ul']
        dataReturn['n_rb_dl'] = n_rb_dl
        dataReturn['n_rb_ul'] = n_rb_ul
        # print("downlink resource blocks", n_rb_dl)
        # print("uplink resource blocks", n_rb_ul)
        return dataReturn
    #配置部分
    def setRate(self):
        url = 'ws://'+self.addr_enb1
        data = {"message": "config_set", "cells": {"1": {"pdsch_fixed_rb_alloc": True,
                                                         "pdsch_fixed_rb_start": 1,
                                                         "pdsch_fixed_l_crb": 272}}}
        data_get = self.loop.run_until_complete(self.connectByWebsocket(url, data))
        print(data_get)


    def cpuinfo_get(self):
        file = open('./cpuinfo.txt', 'r')
        dicts = []
        dict_temp = {}
        for line in file.readlines():
            if line == '\n':
                continue
            line = line.strip()
            k = line.split(':')[0].replace('\t', '')
            v = line.split(':')[1]
            dict_temp[k] = v
            if 'power management' in k:
                dicts.append(dict_temp)
                dict_temp = {}
        file.close()
        dataReturn = []
        for dict in dicts:
            tmp = {}
            tmp['processor'] = dict['processor']
            tmp['model name'] = dict['model name']
            dataReturn.append(tmp)
            # print(dict['processor'])
            # print(dict['model name'])
        return dataReturn
    #Ai部分
    def decode_delay(self,line):
        data = {}
        line = line.strip()
        split_0 = line.split('  ')
        data['T'] = split_0[0].split(':')[1]
        contents = []
        if not split_0[1] == 'items:' and not split_0[1] == 'item':
            items = split_0[1].split(': ')[1].split(', ')
            for item in items:
                item = item.replace(',', '')
                content = item.split(' ')
                contents.append(content)
        data['contents'] = contents
        return data

    def decode_item(self,line):
        confidence_items = []
        line = line.replace('  \n', '')
        items = line.split('  ')
        for item in items:
            confidence = item.split(' ')
            confidence_items.append(confidence[1:])
        return confidence_items

    def AI_get(self):
        print('\n','#'*10,'AI get','#'*10)
        stdin, stdout, stderr = self.client.exec_command("tail -n 1 ./conda_test/yolo_test/yolov5-master/yolodata/item.txt")
        item = stdout.read().decode('utf-8')
        #print(item)
        item_list = self.decode_item(item)
        print(item_list)
        stdin, stdout, stderr = self.client.exec_command("tail -n 1 ./conda_test/yolo_test/yolov5-master/yolodata/time_delay.txt")
        delay = stdout.read().decode('utf-8')
        print(delay)
        delay_dic = self.decode_delay(delay)
        return delay_dic['T']
        
    #更新任务指标
    def update_task(self,datas):
        task_show = []
        if self.window.task['ftp'] == 'Running':
            bitrate = 0
            for ue in datas:
                if ue['imsi'] == self.ismi_ftp:
                    bitrate = ue['dl_bitrate']
            num,bps = convert_bps(bitrate)
            '''
            if len(self.change_enb)<10 and bps == 'Mbps':
                self.change_enb.append(num)
            elif bps == 'Mbps':
                self.change_enb[0:-1]=self.change_enb[1:]
                self.change_enb[-1]=num
            enb_avg = 0
            if len(self.change_enb)==10:
                enb_avg = int(sum(self.change_enb)/len(self.change_enb))
            '''
            if  self.window.task['gnb2'] == 'close' and num>0:# bps == 'Mbps' and enb_avg > self.changeValue_enb:
                self.window.task['gnb2'] = 'start'
                self.change_enb = []
            task_show.append(["FTP业务",'bitrate:'+str(num)+bps])
        if self.window.task['ai0'] == 'Running' or self.window.task['ai1'] == 'Running':
            delay = 0
            len_max = 10
            delay = self.AI_get()
            delay_value=float(delay.replace('ms',''))
            if delay_value>2*self.changeValue_ai:
                delay_value = self.changeValue_ai
            if len(self.change_ai)<len_max:
                self.change_ai.append(delay_value)
            else:
                self.change_ai[0:-1]=self.change_ai[1:]
                self.change_ai[-1]=delay_value
            ai_avg = 0
            if len(self.change_ai)==len_max:
                ai_avg = int(sum(self.change_ai)/len(self.change_ai))
                print(ai_avg)
            if self.window.task['ai0'] == 'close' and self.window.task['gnb2'] == 'Running' and not ai_avg < self.changeValue_ai:
                Thread(target=self.window.changeAi, args=()).start()
                self.change_ai = []
            task_show.append(["目标识别业务",'delay:'+str(delay)])
            self.window.ai_delay_memory[0:-1]=self.window.ai_delay_memory[1:]
            self.window.ai_delay_memory[-1]=delay_value
        #print(task_show)
        self.window.task_show=task_show
        
    #扩容
    #获取基站信息
    def getEnb(self):
        url = 'ws://'+self.addr_mme
        data_send = {"message": "ng_ran"}
        data = self.loop.run_until_complete(self.connectByWebsocket(url, data_send))
        ng_ran_list=data['ng_ran_list']
        return len(ng_ran_list)
        
    #设置增益
    def setDB(self, tx_gain, n):
        enbIp=[self.addr_enb1,self.addr_enb2]
        url = 'ws://' + enbIp[n-1]
        data = {"message": "cell_gain", "cell_id": 1,"gain":tx_gain}
        data_get = self.loop.run_until_complete(self.connectByWebsocket(url, data))
        print(data_get)

    
            
class listen:
    def __init__(self):
        self.connect_time = time.time()
        self.request = ''
        self.count=0
        self.addr = ''

    def start_loop(self, window):
        self.window = window
        # 创建一个服务器的套接字基于udp，type=socket.SOCK_DGRAM表示使用udp协议
        self.udp_sk = socket.socket(type=socket.SOCK_DGRAM)
        self.udp_sk.bind((self.addr_udp, self.port_udp))  # 绑定服务器的ip和端口的套接字
        self.listenRequest()

    def listenRequest(self):
        # udp协议不用建立连接
        while self.window.isVisible():
            msg, addr = self.udp_sk.recvfrom(1024)  # 接收1024字节的消息 msg表示内容，addr表示ip和端口
            self.connect_time=time.time()
            self.addr = addr
            self.request = msg.decode('utf-8')
            print(str(self.addr))
            if self.request == "connect":
                continue
            print(self.request)
            self.window.request = self.request
            
    def sendMsg(self, msg):
            print(msg)
            inp = msg.strip().encode('utf-8')
            if not self.addr == '':
                self.udp_sk.sendto(inp, self.addr)  # 发送消息，需写入对方的ip和端口

                
    def isConnect(self):
        msg = "isConnect"
        inp = msg.strip().encode('utf-8')
        if int(time.time()-self.connect_time)<5:
            return True
        if not self.addr == '':
            self.udp_sk.sendto(inp, self.addr)  # 发送消息，需写入对方的ip和端口
        return False


if __name__ == '__main__':
    #参数设定
    #基站切换阈值
    changeValue_enb = 90
    #ai切换阈值
    changeValue_ai = 1000
    #FTP设备imsi
    ismi_ftp = '001010000000000'
    #与客户端连接
    addr_udp = '192.168.1.12' #udp本机地址
    port_udp = 9554           #udp本机端口
    #node地址配置
    addr_mme = '192.168.1.21:9000'
    addr_enb1 = '192.168.1.2:9001'
    addr_enb2 = '192.168.1.3:9011'
    #AI运行地址
    #ai1
    #ssh地址
    hostname_ai1 = "192.168.1.2"
    username_ai1 = "sdr"
    password_ai1 = "1"
    #拉流地址
    rtmp_ai1 = "rtmp://192.168.1.2:1935/myapp/stream-name"
    #ai2
    #ssh地址
    hostname_ai2 = "192.168.1.21"
    username_ai2 = "sdr"
    password_ai2 = "123123"
    #拉流地址
    rtmp_ai2 = "rtmp://192.168.1.21:1935/myapp/stream-name"
    #ui界面
    myapp = QApplication(sys.argv)
    myDlg = MainDialog()
    myDlg.rtmp_ai1 = rtmp_ai1
    myDlg.rtmp_ai2 = rtmp_ai2
    myDlg.show()
    #数据更新
    update = update()
    update.addr_mme = addr_mme
    update.addr_enb1 = addr_enb1
    update.addr_enb2 = addr_enb2
    update.hostname_ai1 = hostname_ai1
    update.username_ai1 = username_ai1
    update.password_ai1 = password_ai1
    update.hostname_ai2 = hostname_ai2
    update.username_ai2 = username_ai2
    update.password_ai2 = password_ai2
    update.changeValue_enb = changeValue_enb
    update.changeValue_ai = changeValue_ai
    update.ismi_ftp = ismi_ftp
    #客户端监听
    listen = listen()
    listen.addr_udp = addr_udp
    listen.port_udp = port_udp
    myDlg.setSocket(listen)
    #开启线程
    thread1 = Thread(target=update.start_loop, args=(myDlg,))  # 启动线程，刷新页面数据
    thread2 = Thread(target=listen.start_loop, args=(myDlg,))
    thread1.setDaemon(True)
    thread2.setDaemon(True)
    thread1.start()
    thread2.start()
    sys.exit(myapp.exec_())


