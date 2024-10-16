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

class LeaveRequest(models.Model):
    LEAVE_TYPES = (
        ('AL', '年假'),
        ('SL', '病假'),
        ('PL', '事假'),
        ('OL', '其他'),
    )
    STATUS_CHOICES = (
        ('pending', '待审批'),
        ('approved', '已批准'),
        ('rejected', '已拒绝'),
    )
    employee = models.ForeignKey(User, on_delete=models.CASCADE)
    leave_type = models.CharField(max_length=2, choices=LEAVE_TYPES, default='OL')  # 添加默认值
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.TextField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')

    def __str__(self):
        return f"{self.employee}'s {self.get_leave_type_display()} from {self.start_date} to {self.end_date}"

class ApprovalStep(models.Model):
    """
    审批步骤模型
    
    用于定义审批流程中的各个步骤，包括步骤名称、顺序、审批组和指定审批人。
    """
    name = models.CharField(max_length=100, verbose_name="步骤名称")
    order = models.PositiveIntegerField(verbose_name="步骤顺序")
    approver_group = models.ForeignKey(
        Group, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        verbose_name="审批组"
    )
    approver_user = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        verbose_name="指定审批人"
    )

    class Meta:
        ordering = ['order']
        verbose_name = "审批步骤"
        verbose_name_plural = "审批步骤"

    def __str__(self):
        return f"{self.name} (Step {self.order})"

    def get_next_step(self):
        return ApprovalStep.objects.filter(order__gt=self.order).order_by('order').first()

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
    """
    办公用品模型
    
    用于记录可申请的办公用品信息。
    """
    name = models.CharField(max_length=100, verbose_name="物品名称")
    description = models.TextField(blank=True, verbose_name="物品描述")
    unit = models.CharField(max_length=20, default='个', verbose_name="单位")

    class Meta:
        verbose_name = "办公用品"
        verbose_name_plural = "办公用品"

    def __str__(self):
        return self.name

class OfficeSupplyOption(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name

def get_default_supply_option():
    return OfficeSupplyOption.objects.first().id

class SupplyRequest(models.Model):
    """
    办公用品申请模型
    
    用于记录员工的办公用品申请，包括申请人、申请原因、当前状态等信息。
    """
    STATUS_CHOICES = (
        ('pending', '待审批'),
        ('approved', '已批准'),
        ('rejected', '已拒绝'),
    )
    employee = models.ForeignKey(User, on_delete=models.CASCADE, related_name='supply_requests')
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    current_step = models.ForeignKey(
        ApprovalStep, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='current_requests', 
        verbose_name="当前审批步骤"
    )
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")
    current_approver = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='current_approvals')
    next_approver = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='next_approvals')
    current_approval_step = models.IntegerField(default=1)

    class Meta:
        verbose_name = "办公用品申请"
        verbose_name_plural = "办公用品申请"

    def __str__(self):
        return f"Supply Request by {self.employee.username}"

    def get_current_approval(self):
        return self.approvals.filter(step=self.current_step).first()

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

class OfficeSupplyItem(models.Model):
    supply_request = models.ForeignKey(SupplyRequest, on_delete=models.CASCADE, related_name='items')
    supply_option = models.ForeignKey('OfficeSupplyOption', on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()

    def __str__(self):
        return f"{self.supply_option.name} (x{self.quantity})"



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

    supply_request = models.ForeignKey(SupplyRequest, on_delete=models.CASCADE, related_name='approvals')
    approver = models.ForeignKey(User, on_delete=models.CASCADE)
    step = models.ForeignKey(ApprovalStep, on_delete=models.CASCADE)
    status = models.CharField(max_length=20, choices=[('pending', 'Pending'), ('approved', 'Approved'), ('rejected', 'Rejected')])
    comment = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_approved = models.BooleanField(default=False)
    approval_token = models.CharField(max_length=100, unique=True)
    email_sent_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Approval for {self.supply_request} by {self.approver}"

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
                申请人: {self.supply_request.employee.username} <br />
                申请原因: {self.supply_request.reason} <br />

                点击以下链进行审批: <br />
                <a href="{self.get_approve_url(request)}">批准</a> &nbsp;&nbsp;&nbsp;
                <a href="{self.get_reject_url(request)}">拒绝</a>
                """
                # send_mail(subject,"", settings.DEFAULT_FROM_EMAIL, [self.approver.email], html_message=message)
                send_mail(subject,"", from_email, recipient_list, html_message=message) 
            elif self.approver.email.endswith('@qq.com'): # qq邮箱
                message = f"""
                申请人: {self.supply_request.employee.username}
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
            # msg='<a href="http://xxx" target="_blank">��击激活</a>'
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
