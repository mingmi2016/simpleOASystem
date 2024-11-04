import requests
from apscheduler.schedulers.background import BackgroundScheduler
from django_apscheduler.jobstores import DjangoJobStore
from django.conf import settings
from apscheduler.triggers.cron import CronTrigger
from django.utils import timezone
import logging
from . import views
from django.http import HttpRequest
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.db import connection
import sys
import os
from logging.handlers import RotatingFileHandler
import pickle
import base64
from .models import OperationLog
# 确保日志目录存在
log_dir = 'logs'
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

# 设置日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        # 使用 RotatingFileHandler 来自动轮换日志文件
        RotatingFileHandler(
            filename=os.path.join(log_dir, 'scheduler.log'),  # 日志文件路径
            maxBytes=10*1024*1024,  # 每个日志文件最大 10MB
            backupCount=5,          # 保留 5 个备份文件
            encoding='utf-8'        # 使用 UTF-8 编码
        )
    ]
)

logger = logging.getLogger(__name__)

# 全局调度器实例
scheduler = None

class MockRequest:
    """
    模拟 Django 的 HttpRequest 对象。
    在没有实际 HTTP 请求的情况下（如定时任务），这个类可以用来提供必要的请求信息。
    """
    def __init__(self):
        # 设置请求方法为 GET
        self.method = 'GET'
        # 使用匿名用户，因为在定时任务中通常没有认证用户
        self.user = AnonymousUser()
        # 设置一些基本的 META 信息
        self.META = {'REMOTE_ADDR': '127.0.0.1'}
        # 设置协议为 http
        self.scheme = 'http'
        # 定义一个方法来检查是否是安全连接（https）
        self.is_secure = lambda: False
        # 定义一个方法来获取主机名
        self.get_host = lambda: 'localhost:8000'
        
        # 添加 session 支持
        self.session = {}
        
        # 添加 messages 支持
        self._messages = FallbackStorage(self)
        
        # 添加其他必要的属性
        self.POST = {}
        self.GET = {}
        self.COOKIES = {}
        self.path = '/'
        self.resolver_match = None

    def build_absolute_uri(self, path=None):
        """
        构建完整的 URL。
        这个方法模拟了 Django HttpRequest 的 build_absolute_uri 方法。
        """
        host = self.get_host()
        scheme = 'https' if self.is_secure() else 'http'
        if path is None:
            path = '/'
        return f'{scheme}://{host}{path}'

def call_approve_api():
    """
    调用审批 API 并处理返回的数据。
    这个函数被定时任务调用。
    """
    url = "http://127.0.0.1:5000/api/get_approves"

    # 记录日志
    OperationLog.objects.create(
            operator='system',
            operation_type='Scheduler',
            operation_desc=f'定时调度任务执行（call_approve_api）'
        )
    
    try:
        # 发送 GET 请求到审批 API
        response = requests.get(url)
        response.raise_for_status()  # 如果状态码不是200，将引发异常
        data = response.json()
        
        if data['code'] == 200:
            # 创建一个模拟的请求对象
            mock_request = MockRequest()
            # 初始化 session
            middleware = SessionMiddleware(lambda x: x)
            middleware.process_request(mock_request)
            
            process_approve_data(mock_request, data['data'])
        else:
            logger.error(f"API返回错误: {data['msg']}")
        
    except requests.RequestException as e:
        logger.error(f"API调用失败: {e}")
    except Exception as e:
        logger.error(f"处理审批数据时发生错误: {str(e)}")

def process_approve_data(request, approves):
    """
    处理从 API 返回的审批数据。
    
    :param request: HttpRequest 对象或其模拟对象
    :param approves: 包含审批信息的列表
    """
    # print('定时任务执行了。。。。。。。。。。。。。。。。。。。。。。。。。。。。。。。。。。。。。。。。。。。')
    for approve in approves:
        action = approve['action']
        approve_id = approve['id']
        approve_time = approve['time']
        token = approve['token']
        uid = approve['uid']
        
        if action == 'approve':
            print('定时调度任务-审批通过')
            views.process_email_approval(request,approve_id, uid, token, approve=True)
            # 反馈不能放到这里 令牌无效，是不能反馈的，应该是可以的，因为问题在于令牌为什么会无效，而不是反馈的问题，
            # 现有的基础上，令牌无效了，重发邮件应该可以解决问题
            response = requests.get("http://127.0.0.1:5000/api/feedback?id=" + str(approve_id))  # 反馈,更新外部系统的审批状态
        elif action == 'reject':
            print('定时调度任务-审批拒绝')
            views.process_email_approval(request,approve_id, uid, token, approve=False)
            response = requests.get("http://127.0.0.1:5000/api/feedback?id=" + str(approve_id))  # 反馈,更新外部系统的审批状态
        else:
            logger.warning(f"未知的操作类型: {action}")

# def handle_approval(approve_id, approve_time, token, uid):
#     logger.info(f"处理审批: ID {approve_id}, 时间 {approve_time}, 用户 {uid}")
#     # 在这里添加处理审批的逻辑
#     # 例如，更新数据库，发送通知等

def clear_scheduler_jobs():
    """清除所有调度任务"""
    try:
        DjangoJob.objects.all().delete()
        logger.info("All scheduler jobs cleared")
    except Exception as e:
        logger.error(f"Error clearing scheduler jobs: {e}")

def start():
    """启动定时任务调度器"""
    global scheduler
    
    # 如果调度器已经在运行，直接返回
    if scheduler and scheduler.running:
        logger.info("调度器已在运行中")
        return

    try:
        # 清理数据库中的旧任务
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM django_apscheduler_djangojobexecution")
            cursor.execute("DELETE FROM django_apscheduler_djangojob")
            # The command below was not working,and i don't know why
            # cursor.execute("delete from operation_logwhere operation_type = 'Scheduler'")
        
        # 创建新的调度器
        scheduler = BackgroundScheduler(timezone=settings.TIME_ZONE)
        scheduler.add_jobstore(DjangoJobStore(), 'default')
        
        # 添加任务
        scheduler.add_job(
            call_approve_api,
            trigger=CronTrigger(minute="*/1"),
            id="approve_api_job",
            name="Approve API Job",
            replace_existing=True,
            max_instances=1
        )
        
        # 启动调度器
        if not scheduler.running:
            scheduler.start()
            logger.info("调度器启动成功")
        
    except Exception as e:
        logger.error(f"启动调度器时出错: {str(e)}")
        raise

def shutdown():
    """关闭调度器"""
    global scheduler
    if scheduler and scheduler.running:
        scheduler.shutdown()
        scheduler = None
        logger.info("Scheduler shut down successfully")
