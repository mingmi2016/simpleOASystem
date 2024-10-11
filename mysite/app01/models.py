from django.db import models
from django.contrib.auth.models import User, Group
from django.db.models.signals import post_save
from django.dispatch import receiver

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
    employee = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='supply_requests', 
        verbose_name="申请人"
    )
    reason = models.TextField(verbose_name="申请原因")
    status = models.CharField(
        max_length=10, 
        choices=STATUS_CHOICES, 
        default='pending', 
        verbose_name="申请状态"
    )
    current_step = models.ForeignKey(
        ApprovalStep, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='current_requests', 
        verbose_name="当前审批步骤"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        verbose_name = "办公用品申请"
        verbose_name_plural = "办公用品申请"

    def __str__(self):
        return f"{self.employee}'s request on {self.created_at.date()}"

    def get_current_approval(self):
        return self.approvals.filter(step=self.current_step).first()

    def can_be_deleted(self):
        return self.status in ['pending', 'rejected'] and not self.approvals.filter(is_approved=True).exists()

class SupplyRequestItem(models.Model):
    """
    申请物品明细模型
    
    用于记录每个申请中具体申请的物品及其数量。
    """
    supply_request = models.ForeignKey(
        SupplyRequest, 
        on_delete=models.CASCADE, 
        related_name='items', 
        verbose_name="所属申请"
    )
    supply = models.ForeignKey(
        'OfficeSupply', 
        on_delete=models.CASCADE, 
        verbose_name="申请物品"
    )
    quantity = models.PositiveIntegerField(verbose_name="申请数量")

    class Meta:
        verbose_name = "申请物品明细"
        verbose_name_plural = "申请物品明细"

    def __str__(self):
        return f"{self.supply.name} ({self.quantity}) for {self.supply_request}"

class RequestApproval(models.Model):
    """
    审批记录模型
    
    用于记录每个申请在各个审批步骤中的审批情况。
    """
    supply_request = models.ForeignKey(
        SupplyRequest, 
        on_delete=models.CASCADE, 
        related_name='approvals', 
        verbose_name="所属申请"
    )
    step = models.ForeignKey(
        ApprovalStep, 
        on_delete=models.CASCADE, 
        verbose_name="审批步骤"
    )
    approver = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        verbose_name="审批人"
    )
    is_approved = models.BooleanField(null=True, blank=True, verbose_name="是否批准")
    comment = models.TextField(blank=True, verbose_name="审批意见")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        ordering = ['step__order']
        verbose_name = "审批记录"
        verbose_name_plural = "审批记录"

    def __str__(self):
        return f"{self.step.name} for {self.supply_request}"