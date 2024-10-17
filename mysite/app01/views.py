from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from .models import LeaveRequest, ApprovalStep, SupplyRequest, OfficeSupplyItem
from .forms import LeaveRequestForm, SupplyRequestForm, OfficeSupplyItemFormSet, RequestApprovalForm
from django.utils import timezone
from django.db import transaction
from .models import SupplyRequest, RequestApproval, ApprovalStep
from django.contrib.auth.models import User
from django.contrib import messages
from django.db.models import F, Prefetch
from .models import RequestApproval, SupplyRequest
from django.core.paginator import Paginator
from django.db.models import Q
from django.core.mail import send_mail
from django.urls import reverse
from django.conf import settings
import logging
from smtplib import SMTPException
from django.core.exceptions import ObjectDoesNotExist
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.db.models import Max
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from django.utils.http import urlsafe_base64_decode
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.conf import settings

logger = logging.getLogger(__name__)

@login_required
def create_leave_request(request):
    if request.method == 'POST':
        form = LeaveRequestForm(request.POST)
        if form.is_valid():
            leave_request = form.save(commit=False)
            leave_request.employee = request.user
            leave_request.save()
            return redirect('leave_request_list')
    else:
        form = LeaveRequestForm()
    return render(request, 'app01/create_leave_request.html', {'form': form})

@login_required
def leave_request_detail(request, pk):
    leave_request = get_object_or_404(LeaveRequest, pk=pk)
    return render(request, 'app01/leave_request_detail.html', {'leave_request': leave_request})

@login_required
def approve_leave_request(request, pk):
    leave_request = get_object_or_404(LeaveRequest, pk=pk)
    approval_step = leave_request.approval_steps.filter(approver=request.user, is_approved=False).first()
    
    if request.method == 'POST':
        action = request.POST.get('action')
        comment = request.POST.get('comment', '')
        
        if action == 'approve':
            approval_step.is_approved = True
            approval_step.comment = comment
            approval_step.approved_at = timezone.now()
            approval_step.save()
            
            if not leave_request.approval_steps.filter(is_approved=False).exists():
                leave_request.status = 'approved'
                leave_request.save()
        elif action == 'reject':
            leave_request.status = 'rejected'
            leave_request.save()
            approval_step.comment = comment
            approval_step.save()
        
        return redirect('leave_request_detail', pk=leave_request.pk)
    
    return render(request, 'approve_leave_request.html', {'leave_request': leave_request, 'approval_step': approval_step})


@login_required
def create_leave_request(request):
    if request.method == 'POST':
        form = LeaveRequestForm(request.POST)
        if form.is_valid():
            leave_request = form.save(commit=False)
            leave_request.employee = request.user
            leave_request.save()
            
            # 创建审批步骤
            if request.user.profile.direct_manager:
                ApprovalStep.objects.create(
                    leave_request=leave_request,
                    approver=request.user.profile.direct_manager,
                    order=1
                )
            
            if request.user.profile.department and request.user.profile.department.head:
                ApprovalStep.objects.create(
                    leave_request=leave_request,
                    approver=request.user.profile.department.head,
                    order=2
                )
            
            return redirect('leave_request_detail', pk=leave_request.pk)
    else:
        form = LeaveRequestForm()
    return render(request, 'create_leave_request.html', {'form': form})


#  views.py 中使用这个函数
from .utils import get_approvers

@login_required
def create_leave_request(request):
    if request.method == 'POST':
        form = LeaveRequestForm(request.POST)
        if form.is_valid():
            leave_request = form.save(commit=False)
            leave_request.employee = request.user
            leave_request.save()
            
            # 使用 get_approvers 函数来创建审批步
            for approver, order in get_approvers(request.user):
                ApprovalStep.objects.create(
                    leave_request=leave_request,
                    approver=approver,
                    order=order
                )
            
            return redirect('leave_request_detail', pk=leave_request.pk)
    else:
        form = LeaveRequestForm()
    return render(request, 'create_leave_request.html', {'form': form})

from django.shortcuts import render
from .models import LeaveRequest

def leave_request_list(request):
    leave_requests = LeaveRequest.objects.all()
    return render(request, 'app01/leave_request_list.html', {'leave_requests': leave_requests})

# 留你之前定义的其他视图函数
# ...

@user_passes_test(lambda u: u.is_staff)
def approve_leave_request(request, pk):
    leave_request = get_object_or_404(LeaveRequest, pk=pk)
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'approve':
            leave_request.status = 'approved'
        elif action == 'reject':
            leave_request.status = 'rejected'
        leave_request.save()
    return redirect('leave_request_detail', pk=pk)



@login_required
def supply_request_detail(request, pk):
    supply_request = get_object_or_404(SupplyRequest, pk=pk)
    approvals = supply_request.approvals.all().order_by('step__order')
    return render(request, 'app01/supply_request_detail.html', {
        'supply_request': supply_request,
        'approvals': approvals,
    })

@login_required
def approval_list(request):
    # 获取用可审批的所有步骤
    user_approval_steps = ApprovalStep.objects.filter(
        Q(approver_user=request.user) | Q(approver_group__user=request.user)
    )

    # 获取待审批的请求
    pending_approvals = RequestApproval.objects.filter(
        step__in=user_approval_steps,
        is_approved=None,
        supply_request__current_step__in=user_approval_steps
    ).select_related('supply_request', 'step', 'supply_request__current_step')

    return render(request, 'app01/approval_list.html', {'pending_approvals': pending_approvals})

# @login_required
@transaction.atomic
def approve_request(request, approval_id):
    approval = get_object_or_404(RequestApproval, id=approval_id, approver=request.user, status='pending')
    
    if request.method == 'POST':
        action = request.POST.get('action')
        comment = request.POST.get('comment', '')
        
        if action in ['approve', 'reject']:
            approval.status = 'approved' if action == 'approve' else 'rejected'
            approval.comment = comment
            approval.save()
            
            process_next_approval_step(approval.supply_request)
            
            messages.success(request, '审批操作已完成')
        else:
            messages.error(request, '无效的操作')
        
        return redirect('pending_approvals')
    
    return render(request, 'app01/approve_request.html', {'approval': approval})

def get_approver_for_step(step):
    if step.approver_user:
        return step.approver_user
    elif step.approver_group:
        return step.approver_group.user_set.first()  # 你可能需要一个更复杂的逻来选择组的审批人
    return None

def update_request_status(supply_request):
    approvals = supply_request.approvals.all()
    if all(approval.is_approved for approval in approvals):
        supply_request.status = 'approved'
    elif any(approval.is_approved == False for approval in approvals):
        supply_request.status = 'rejected'
    supply_request.save()

@login_required
def supply_request_list(request):
    supply_requests = SupplyRequest.objects.filter(employee=request.user).order_by('-created_at')

    # 为每个供应请求预先获取相关的办公用品项目
    supply_requests_with_items = []
    for supply_request in supply_requests:
        items = OfficeSupplyItem.objects.filter(supply_request=supply_request)
        supply_requests_with_items.append({
            'request': supply_request,
            'items': items
        })

    context = {
        'supply_requests': supply_requests_with_items
    }
    return render(request, 'app01/supply_request_list.html', context)

@login_required
def approval_list(request):
    print(f"Current user: {request.user}")
    pending_approvals = RequestApproval.objects.filter(approver=request.user, is_approved=None)
    print(f"Pending approvals: {pending_approvals.count()}")
    for approval in pending_approvals:
        print(f"Approval ID: {approval.id}, Supply Request: {approval.supply_request}, Step: {approval.step}")
    return render(request, 'app01/approval_list.html', {'pending_approvals': pending_approvals})


# 这个是之的老流程，通过点击审批不用了
# @login_required
# def approve_request(request, approval_id):
#     approval = get_object_or_404(RequestApproval, id=approval_id, approver=request.user)
#     if request.method == 'POST':
#         form = RequestApprovalForm(request.POST, instance=approval)
#         if form.is_valid():
#             form.save()
#             # 检查是否所步骤都已审批
#             supply_request = approval.supply_request
#             all_approved = all(a.is_approved for a in supply_request.approvals.all())
#             if all_approved:
#                 supply_request.status = 'approved'
#             elif approval.is_approved == False:  # 如果有任何一步被拒绝
#                 supply_request.status = 'rejected'
#             supply_request.save()
#             return redirect('approval_list')
#     else:
#         form = RequestApprovalForm(instance=approval)
#     return render(request, 'app01/approve_request.html', {'form': form, 'approval': approval})

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from .models import ApprovalStep
from .forms import ApprovalStepForm

def is_admin(user):
    return user.is_superuser or user.is_staff

@login_required
@user_passes_test(is_admin)
def approval_step_list(request):
    steps = ApprovalStep.objects.all().order_by('order')
    return render(request, 'app01/approval_step_list.html', {'steps': steps})

@login_required
@user_passes_test(is_admin)
def approval_step_create(request):
    if request.method == 'POST':
        form = ApprovalStepForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('approval_step_list')
    else:
        form = ApprovalStepForm()
    return render(request, 'app01/approval_step_form.html', {'form': form})

@login_required
@user_passes_test(is_admin)
def approval_step_edit(request, pk):
    step = get_object_or_404(ApprovalStep, pk=pk)
    if request.method == 'POST':
        form = ApprovalStepForm(request.POST, instance=step)
        if form.is_valid():
            form.save()
            return redirect('approval_step_list')
    else:
        form = ApprovalStepForm(instance=step)
    return render(request, 'app01/approval_step_form.html', {'form': form})

@login_required
@user_passes_test(is_admin)
def approval_step_delete(request, pk):
    step = get_object_or_404(ApprovalStep, pk=pk)
    if request.method == 'POST':
        step.delete()
        return redirect('approval_step_list')
    return render(request, 'app01/approval_step_confirm_delete.html', {'step': step})

from django.shortcuts import render

def index(request):
    return render(request, 'app01/index.html')

def is_admin_or_creator(user):
    return user.is_staff or user.is_superuser

@login_required
@user_passes_test(is_admin_or_creator)
def delete_supply_request(request, pk):
    supply_request = get_object_or_404(SupplyRequest, pk=pk)
    
    if request.user == supply_request.employee or request.user.is_staff or request.user.is_superuser:
        if supply_request.can_be_deleted():
            supply_request.delete()
            messages.success(request, '供应请求已成功删除。')
        else:
            messages.error(request, '无法删除此供应请求，因为它已经开始审批或已被批准。')
    else:
        messages.error(request, '你没有权限删除此供应请。')
    
    return redirect('approval_list')

@login_required
def approval_history(request):
    # 获取所有的供应请求
    supply_requests = SupplyRequest.objects.all().order_by('-created_at')
    
    # 为每个供应请求获取其审批历史相关的办公用品项目
    approval_history = []
    for supply_request in supply_requests:
        approvals = RequestApproval.objects.filter(supply_request=supply_request).order_by('created_at')
        items = OfficeSupplyItem.objects.filter(supply_request=supply_request)
        approval_history.append({
            'supply_request': supply_request,
            'approvals': approvals,
            'items': items
        })
    
    context = {
        'approval_history': approval_history
    }
    return render(request, 'app01/approval_history.html', context)

@login_required
def pending_approvals(request):
    approvals = RequestApproval.objects.filter(approver=request.user, status='pending')
    return render(request, 'app01/pending_approvals.html', {'approvals': approvals})


from django.core.mail import EmailMessage
from django.utils.encoding import force_bytes

def send_approval_email(supply_request, approver):
    current_approval = supply_request.get_current_approval()
    approve_token = default_token_generator.make_token(approver)
    uid = urlsafe_base64_encode(force_bytes(approver.pk))
    
    approve_url = reverse('approve_request_email', kwargs={
        'approval_id': current_approval.id,
        'uidb64': uid,
        'token': approve_token,
        'action': 'approve'
    })
    reject_url = reverse('approve_request_email', kwargs={
        'approval_id': current_approval.id,
        'uidb64': uid,
        'token': approve_token,
        'action': 'reject'
    })
    
    site_url = settings.SITE_URL.rstrip('/')
    approve_url = f"{site_url}{approve_url}"
    reject_url = f"{site_url}{reject_url}"

    print(f"Debug: SITE_URL = {settings.SITE_URL}")  # 调试信息
    print(f"Debug: site_url = {site_url}")  # 调试信息
    print(f"Debug: approve_url = {approve_url}")  # 调试信息
    print(f"Debug: reject_url = {reject_url}")  # 调试信息

    subject = f'办公用品申请审批 - 申请编号 {supply_request.id}'
    message = f"""
    您好 {approver.username}，

    有一个新的办公用品申请需要您审批。

    申请人: {supply_request.employee}
    申请原因: {supply_request.reason}

    申请物品:
    {', '.join([f"{item.name} ({item.quantity})" for item in supply_request.items.all()])}

    请点击以下链接进行审批：
    
    批准: {approve_url}
    
    拒绝: {reject_url}

    或者您可以登录系统进行更详细的审批操作。

    谢谢！
    """
    
    send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [approver.email], fail_silently=False)
    print(f"Approval email sent to {approver.email}")  # 添加日志

@login_required
def email_approve(request, approval_id, uidb64, token, action):
    try:
        uid = urlsafe_base64_decode(uidb64).decode()
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user is not None and default_token_generator.check_token(user, token):
        approval = get_object_or_404(RequestApproval, id=approval_id, approver=user, status='pending')
        
        if action == 'approve':
            approval.status = 'approved'
            approval.save()
            process_next_approval_step(approval.supply_request)
            messages.success(request, '申请已批准')
        elif action == 'reject':
            approval.status = 'rejected'
            approval.save()
            approval.supply_request.status = 'rejected'
            approval.supply_request.save()
            messages.success(request, '申请已拒绝')
        else:
            messages.error(request, '无效的操作')
            return redirect('home')
        
        return redirect('approval_success')
    else:
        messages.error(request, '无效的审批链接')
        return redirect('approval_error')

def reject_request(request, token):
    approval = get_object_or_404(RequestApproval, approval_token=token)
    if approval.status == 'pending':
        approval.status = 'rejected'
        approval.save()
        messages.success(request, '请求已被拒绝。')
    else:
        messages.error(request, '此请求已经被处理过了。')
    return redirect('some_appropriate_url_name')  # 替换为适当的URL称

# def approve_request(request, token):
#     approval = get_object_or_404(RequestApproval, approval_token=token)
#     if approval.status == 'pending':
#         approval.status = 'approved'
#         approval.save()
#         messages.success(request, '请求已被批准。')
#     else:
#         messages.error(request, '此请求已经被处理过了。111')
#     return redirect('home')  # 或者 return render(request, 'some_template.html')

@login_required
def supply_request_detail(request, pk):
    supply_request = get_object_or_404(SupplyRequest, pk=pk)
    return render(request, 'app01/supply_request_detail.html', {'supply_request': supply_request})

@login_required
def approval_process(request, request_id):
    supply_request = SupplyRequest.objects.get(id=request_id)
    approvals = RequestApproval.objects.filter(supply_request=supply_request).order_by('step__order')
    
    context = {
        'supply_request': supply_request,
        'approvals': approvals,
    }
    return render(request, 'app01/approval_process.html', context)



@login_required
def approval_process_settings(request):
    steps = ApprovalStep.objects.all().order_by('order')
    
    if request.method == 'POST':
        form = ApprovalStepForm(request.POST)
        if form.is_valid():
            new_step = form.save(commit=False)
            max_order = ApprovalStep.objects.aggregate(Max('order'))['order__max']
            new_step.order = (max_order or 0) + 1
            new_step.save()
            messages.success(request, '新的审批步骤已添加。')
            return redirect('approval_process_settings')
        else:
            messages.error(request, f'表单验证失败: {form.errors}')
    else:
        form = ApprovalStepForm()
    
    context = {
        'steps': steps,
        'form': form,
    }
    return render(request, 'app01/approval_process_settings.html', context)

@login_required
def edit_approval_step(request, step_id):
    step = get_object_or_404(ApprovalStep, id=step_id)
    if request.method == 'POST':
        form = ApprovalStepForm(request.POST, instance=step)
        if form.is_valid():
            form.save()
            messages.success(request, '审批步骤已更新')
            return redirect('approval_process_settings')
    else:
        form = ApprovalStepForm(instance=step)
    
    return render(request, 'app01/edit_approval_step.html', {
        'form': form,
        'step': step
    })

@login_required
def delete_approval_step(request, step_id):
    step = get_object_or_404(ApprovalStep, id=step_id)
    step.delete()
    messages.success(request, '审批步骤已删除')
    return redirect('approval_process_settings')

from django.urls import reverse
from django.core.mail import send_mail
from django.conf import settings

# old code
# def send_approval_email(request, supply_request, approver):
#     subject = f'办公用品申请审批 - 申请编号 {supply_request.id}'
#     message = f"""
#     您好 {approver.username}，

#     有一个新的办公用品申请需要您审批。

#     申请: {supply_request.employee}
#     申请原因: {supply_request.reason}

#     申请物品:
#     {', '.join([f"{item.supply_option.name} ({item.quantity})" for item in supply_request.items.all()])}

#     请登录系统进行审批。

#     谢谢！
#     """
    
#     from_email = settings.DEFAULT_FROM_EMAIL
#     recipient_list = [approver.email]
    
#     send_mail(subject, message, from_email, recipient_list, fail_silently=False)



def send_approval_email(supply_request, approver):
    # 生成审批链接
    approve_token = default_token_generator.make_token(approver)
    uid = urlsafe_base64_encode(force_bytes(approver.pk))
    approval = RequestApproval.objects.get(supply_request=supply_request, approver=approver, status='pending')
    
    approve_url = reverse('approve_request_email', kwargs={
        'approval_id': approval.id,
        'uidb64': uid,
        'token': approve_token
    })
    reject_url = reverse('reject_request_email', kwargs={
        'approval_id': approval.id,
        'uidb64': uid,
        'token': approve_token
    })
    
    site_url = settings.SITE_URL.rstrip('/')
    approve_url = f"{site_url}{approve_url}"
    reject_url = f"{site_url}{reject_url}"

    subject = f'办公用品申请审批 - 申请编号 {supply_request.id}'
    message = f"""
    您好 {approver.username}，

    有一个新的办公用品申请需要您审批。

    申请人: {supply_request.employee}
    申请原因: {supply_request.reason}

    申请物品:
    {', '.join([f"{item.supply_option.name} ({item.quantity})" for item in supply_request.items.all()])}

    请点击以下链接进行审批：
    
    批准: {approve_url}
    
    拒绝: {reject_url}

    或者您可以登录系统进行更详细的审批操作。

    谢谢！
    """
    
    from_email = settings.DEFAULT_FROM_EMAIL
    recipient_list = [approver.email]
    
    send_mail(subject, message, from_email, recipient_list, fail_silently=False)

def email_approve(request, approval_id, uidb64, token, action):
    try:
        uid = urlsafe_base64_decode(uidb64).decode()
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user is not None and default_token_generator.check_token(user, token):
        approval = get_object_or_404(RequestApproval, id=approval_id, approver=user, status='pending')
        
        if action == 'approve':
            approval.status = 'approved'
            approval.save()
            process_next_approval_step(approval.supply_request)
            messages.success(request, '申请已批准')
        elif action == 'reject':
            approval.status = 'rejected'
            approval.save()
            approval.supply_request.status = 'rejected'
            approval.supply_request.save()
            messages.success(request, '申请已拒绝')
        else:
            messages.error(request, '无效的操作')
            return redirect('home')
        
        return redirect('approval_success')
    else:
        messages.error(request, '无效的审批链接')
        return redirect('approval_error')

@login_required
def create_supply_request(request):
    if request.method == 'POST':
        form = SupplyRequestForm(request.POST)
        formset = OfficeSupplyItemFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            supply_request = form.save(commit=False)
            supply_request.employee = request.user
            supply_request.save()
            
            formset.instance = supply_request
            formset.save()
            
            # 创建第一个审批步骤
            first_step = ApprovalStep.objects.order_by('order').first()
            if first_step:
                RequestApproval.objects.create(
                    supply_request=supply_request,
                    step=first_step,
                    approver=first_step.approver_user,
                    status='pending'
                )
                send_approval_email(supply_request, first_step.approver_user)  # 修改这里
            
            messages.success(request, '申请已提交，等待审批')
            return redirect('supply_request_list')
    else:
        form = SupplyRequestForm()
        formset = OfficeSupplyItemFormSet()
    
    context = {
        'form': form,
        'formset': formset,
    }
    return render(request, 'app01/create_supply_request.html', context)










@login_required
@require_POST
def update_step_order(request):
    step_ids = request.POST.getlist('step_ids[]')
    for index, step_id in enumerate(step_ids, start=1):
        ApprovalStep.objects.filter(id=step_id).update(order=index)
    return JsonResponse({'status': 'success'})

User = get_user_model()

def approve_request_email(request, approval_id, uidb64, token):
    return process_email_approval(request, approval_id, uidb64, token, approve=True)

def reject_request_email(request, approval_id, uidb64, token):
    return process_email_approval(request, approval_id, uidb64, token, approve=False)

def process_email_approval(request, approval_id, uidb64, token, approve):
    try:
        uid = urlsafe_base64_decode(uidb64).decode()
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user is not None and default_token_generator.check_token(user, token):
        approval = get_object_or_404(RequestApproval, id=approval_id, approver=user, status='pending')
        
        if approve:
            approval.status = 'approved'
            approval.save()
            process_next_approval_step(approval.supply_request)
            messages.success(request, '申请已批准')
        else:
            approval.status = 'rejected'
            approval.save()
            approval.supply_request.status = 'rejected'
            approval.supply_request.save()
            messages.success(request, '申请已拒绝')
        
        return redirect('approval_success')
    else:
        messages.error(request, '无效的审链接')
        return redirect('approval_error')

@transaction.atomic
def process_next_approval_step(supply_request):
    current_approval = supply_request.get_current_approval()
    print(f"Current approval for supply request {supply_request.id}: {current_approval}")
    
    if current_approval is None:
        print(f"No approvals found for supply request {supply_request.id}")
        return

    if current_approval.status == 'approved':
        next_step = current_approval.step.get_next_step()
        if next_step:
            next_approval = RequestApproval.objects.create(
                supply_request=supply_request,
                step=next_step,
                approver=next_step.approver_user,
                status='pending'
            )
            send_approval_email(supply_request, next_step.approver_user)
            print(f"Created next approval step: {next_approval}")
        else:
            supply_request.status = 'approved'
            supply_request.save()
            print(f"Supply request {supply_request.id} has been fully approved")
    elif current_approval.status == 'pending':
        print(f"Current approval is still pending for supply request {supply_request.id}")
    else:
        print(f"Unexpected status '{current_approval.status}' for current approval of supply request {supply_request.id}")

    all_approvals = supply_request.approvals.all().order_by('step__order')
    print(f"All approvals for supply request {supply_request.id}:")
    for approval in all_approvals:
        print(f"  - Step: {approval.step.order}, Status: {approval.status}, Approver: {approval.approver}")

def approval_success(request):
    return render(request, 'app01/approval_success.html')

def approval_error(request):
    return render(request, 'app01/approval_error.html')