import uuid
from django.core.mail import send_mail
from django.conf import settings
from django.urls import reverse
import logging

logger = logging.getLogger(__name__)

def get_approvers(employee):
    approvers = []
    if employee.profile.direct_manager:
        approvers.append((employee.profile.direct_manager, 1))
    if employee.profile.department and employee.profile.department.head:
        approvers.append((employee.profile.department.head, 2))
    # 可以添加更多的逻辑来确定其他审批人
    return approvers

def generate_approval_token():
    return uuid.uuid4().hex

def send_approval_email(request, request_approval):
    subject = f'办公用品申请审批 - 申请编号 {request_approval.supply_request.id}'
    approve_url = request.build_absolute_uri(
        reverse('approve_request', args=[request_approval.id])
    )
    message = f"""
    您好，

    有一个新的办公用品申请需要您审批。

    申请人: {request_approval.supply_request.employee}
    申请原因: {request_approval.supply_request.reason}

    申请物品:
    {', '.join([f"{item.supply_option.name} ({item.quantity})" for item in request_approval.supply_request.items.all()])}

    请登录系统进行审批：
    {approve_url}

    谢谢！
    """
    
    send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        [request_approval.approver.email],
        fail_silently=False,
    )

def send_final_result_email(request, supply_request):
    logger.info(f"Attempting to send final result email for supply request {supply_request.id}")
    subject = f'办公用品申请结果 - 申请编号 {supply_request.id}'
    message = f"""
    您好，

    您的办公用品申请（申请编号：{supply_request.id}）已经完成审批流程。

    申请结果：{'已通过' if supply_request.is_approved() else '未通过'}

    申请物品：
    {', '.join([f"{item.supply_option.name} ({item.quantity})" for item in supply_request.items.all()])}

    如有任何疑问，请联系相关部门。

    谢谢！
    """
    
    try:
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [supply_request.employee.email],
            fail_silently=False,
        )
        logger.info(f"Final result email sent for supply request {supply_request.id}")
    except Exception as e:
        logger.error(f"Failed to send final result email for supply request {supply_request.id}: {str(e)}")

def get_next_approver(supply_request):
    # 获取当前审批步骤
    current_step = supply_request.current_approval_step()
    if current_step:
        # 获取下一个审批步骤
        next_step = ApprovalStep.objects.filter(order__gt=current_step.order).first()
        if next_step:
            if next_step.approver_user:
                return next_step.approver_user
            elif next_step.approver_group:
                # 如果是组，可能需要选择组中的一个成员
                return next_step.approver_group.user_set.first()
    return None

