from django.db import models
from django.contrib.auth.models import User, Group
from django.db.models.signals import post_save
from django.dispatch import receiver
from .utils import generate_approval_token
from django.utils import timezone
import smtplib
import uuid

from django.core.mail import send_mail
from django.utils.encoding import force_str
from django.conf import settings
import logging

from django.urls import reverse
from email.mime.text import MIMEText
from email.header import Header


logger = logging.getLogger(__name__)


class ApprovalStep(models.Model):
    """
    审批步骤模型
    
    用于记录每个审批步骤的详细信息，包括审批人、审批顺序等。
    """
    process_name = models.CharField(max_length=100)
    step_number = models.IntegerField(unique=True, verbose_name="步骤编号")
    approvers = models.ManyToManyField(User, related_name='approval_steps')
    is_countersign = models.BooleanField(default=False, help_text="是否为会签步骤")
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)
    order = models.IntegerField(unique=True, verbose_name="排序")

    class Meta:
        unique_together = ['process_name', 'step_number']
        ordering = ['order']

    def __str__(self):
        return f"步骤 {self.step_number}"

    def get_next_step(self):
        return ApprovalStep.objects.filter(process_name=self.process_name, step_number__gt=self.step_number).order_by('step_number').first()

    def get_approvers(self):
        return list(self.approvers.all())

    def get_approver(self):
        return self.approvers.all().first()

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    is_manager = models.BooleanField(default=False)  # 这里缺少默认值
    # 添加你需要的其他字段
    
    def __str__(self):
        return self.user.username

    @classmethod
    def get_or_create(cls, user):
        try:
            return user.profile
        except cls.DoesNotExist:
            return cls.objects.create(user=user)

class Department(models.Model):
    name = models.CharField(max_length=100)
    head = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='headed_department')

    def __str__(self):
        return self.name

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    instance.profile.save()

class OfficeSupply(models.Model):
    name = models.CharField(max_length=100)
    # 其他字段...

    def __str__(self):
        return self.name

# class OfficeSupplyOption(models.Model):
#     name = models.CharField(max_length=100)

#     def __str__(self):
#         return self.name

# def get_default_supply_option():
#     return OfficeSupplyOption.objects.first().id

def get_default_user():
    return User.objects.get_or_create(username='default_user')[0].id

class SupplyRequest(models.Model):
    """
    办公用品申请模型
    
    用于记录员工的办公用品申请，包括申请人、申请因、当前状态等信息。
    """
    requester = models.ForeignKey(User, on_delete=models.CASCADE)
    purpose = models.TextField()
    status = models.CharField(max_length=20, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    current_step = models.ForeignKey('ApprovalStep', on_delete=models.SET_NULL, null=True, blank=True)
    
    # 其他字段...

    class Meta:
        verbose_name = "办公用品申请"
        verbose_name_plural = "办公用品申请"

    def __str__(self):
        return f"申请 #{self.id} - {self.requester.username} - {self.get_status_display()}"

    def get_current_approval(self):
        return self.requestapproval_set.order_by('-created_at').first()

    def can_be_deleted(self):
        return self.status in ['pending', 'rejected'] and not self.approvals.filter(is_approved=True).exists()

    def get_next_approver(self):
        if self.next_approver:
            current = self.current_approver
            self.current_approver = self.next_approver
            self.next_approver = None
            self.save()
            return current
        return None

    def move_to_next_approval(self):

        next_approval = self.requestapproval_set.filter(
                status='pending'
            ).first()
            
        if next_approval:
           return next_approval
        
        return None

    def is_approved(self):
        return all(approval.status == 'approved' for approval in self.requestapproval_set.all())

class SupplyRequestItem(models.Model):
    supply_request = models.ForeignKey(SupplyRequest, on_delete=models.CASCADE, related_name='items')
    office_supply = models.ForeignKey(OfficeSupply, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()

    def __str__(self):
        return f"{self.office_supply.name} - {self.quantity}"



class RequestApproval(models.Model):
    """
    审批记录模型
    
    用于记录每个申请在各个审批步骤中的审批情况。
    """
    STATUS_CHOICES = (
        ('pending', '待审批'),
        ('approved', '已批准'),
        ('rejected', '已拒绝'),
    )


    supply_request = models.ForeignKey(SupplyRequest, on_delete=models.CASCADE)
    approver = models.ForeignKey(User, on_delete=models.CASCADE)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    comment = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    step = models.ForeignKey(ApprovalStep, on_delete=models.CASCADE)

    def __str__(self):
        return f"审批 {self.id} - {self.approver.username} - {self.get_status_display()}"

    @staticmethod
    def generate_token():
        return uuid.uuid4().hex

    def send_approval_email(self, request):
        try:
            subject = f'***审批: {self.supply_request.reason}'
            from_email = settings.DEFAULT_FROM_EMAIL
            recipient_list = [self.approver.email]

            if self.approver.email.endswith('@163.com') or self.approver.email.endswith('njau.edu.cn'): # 163邮箱
                message = f"""
                申请人: {self.supply_request.requester.username} <br />
                申请原因: {self.supply_request.reason} <br />

                点击以下链进行审批: <br />
                <a href="{self.get_approve_url(request)}">批准</a> &nbsp;&nbsp;&nbsp;
                <a href="{self.get_reject_url(request)}">拒绝</a>
                """
                # send_mail(subject,"", settings.DEFAULT_FROM_EMAIL, [self.approver.email], html_message=message)
                send_mail(subject,"", from_email, recipient_list, html_message=message) 
            elif self.approver.email.endswith('@qq.com'): # qq邮箱
                message = f"""
                申请人: {self.supply_request.requester.username}
                申请原因: {self.supply_request.reason}

                点击以下接进行审批:
                批准: {self.get_approve_url(request)}
                拒绝: {self.get_reject_url(request)}
                """
                send_mail(
                    subject,
                    message,
                    from_email,
                    recipient_list,
                    fail_silently=False,
                )
            else:
                pass    

            # print(html_message)
            # 163邮箱 写法
            # html_message = '<p>尊敬的用户您好！</p>' \
            #            '<p>感谢您使用XXXX。</p>' \
            #            '<p>您的邮箱为：%s 。请点击此链接激活您的邮箱：</p>' \
            #            '<p><a href="%s">%s<a></p>' % ('22@qq.com', f'http://127.0.0.1:8000/app01/reject/465bee060fdd461faa72355a9b13ee84/', '222')
            # # send_mail(subject,"", settings.DEFAULT_FROM_EMAIL, [self.approver.email], html_message=html_message)
            # msg='<a href="http://xxx" target="_blank">击激活</a>'
            # send_mail('注册激活','',settings.DEFAULT_FROM_EMAIL, ['t2024087@njau.edu.cn'], html_message=msg)
            # send_mail(subject,'',settings.DEFAULT_FROM_EMAIL, [self.approver.email], html_message=html_message)

            self.email_sent_at = timezone.now()
            self.save(update_fields=['email_sent_at'])
            
            logger.info(f"Approval email sent successfully to {self.approver.email}")
        except Exception as e:
            logger.error(f"Failed to send approval email: {str(e)}")
            raise

    def get_approve_url(self, request):
        return request.build_absolute_uri(reverse('approve_request', args=[self.approval_token]))

    def get_reject_url(self, request):
        return request.build_absolute_uri(reverse('reject_request', args=[self.approval_token]))


@receiver(post_save, sender=SupplyRequest)
def supply_request_post_save(sender, instance, created, **kwargs):
    if created:
        # 确保这里没有重复调用发送邮件的函数
        pass

@receiver(post_save, sender=RequestApproval)
def request_approval_post_save(sender, instance, created, **kwargs):
    if created:
        # 确保这里没有重复调用发送邮件的函数
        pass






class OperationLog(models.Model):
    # 操作类型选项
    OPERATION_CHOICES = [
        ('Send_Email', '发送邮件'),
        ('Email_Approve', '邮件审批'),
        ('System_Approve', '系统审批'),
        ('Approve_Finish', '审批完成'),
        ('Resend_Email', '重发邮件'),
        ('Exception', '异常'),
        ('OTHER', '其他'),
    ]

    # 基本字段
    operator = models.CharField(max_length=100, verbose_name='操作人')
    operation_type = models.CharField(
        max_length=20, 
        choices=OPERATION_CHOICES,
        verbose_name='操作类型'
    )
    operation_desc = models.CharField(max_length=500, verbose_name='操作描述')
    operation_time = models.DateTimeField(default=timezone.now, verbose_name='操作时间')

    class Meta:
        verbose_name = '操作日志'
        verbose_name_plural = '操作日志'
        ordering = ['-operation_time']
        db_table = 'operation_log'

    def __str__(self):
        return f"{self.operator} - {self.get_operation_type_display()} - {self.operation_time}"
