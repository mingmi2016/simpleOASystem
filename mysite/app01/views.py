from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from .models import LeaveRequest, ApprovalStep, SupplyRequest, OfficeSupplyItem, OfficeSupplyOption
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

# 保留你之前定义的其他视图函数
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
    # 获取用户可以审批的所有步骤
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
def approve_request(request, token):
    approval = get_object_or_404(RequestApproval, approval_token=token)
    supply_request = approval.supply_request  # 将这行移到函数开始处
    
    if approval.status == 'pending':
        approval.status = 'approved'
        approval.save()
        
        next_approval = supply_request.move_to_next_approval()
        
        if next_approval:
            messages.success(request, '审批请求已准已进入下一个审批步。')
            next_approval.send_approval_email(request)
        else:
            supply_request.status = 'approved'
            supply_request.save()
            messages.success(request, '审批请求已最终批准，供应请求完成。')
    else:
        messages.error(request, '此请求经被处理过了。')
    
    return redirect('supply_request_detail', pk=supply_request.pk)

def get_approver_for_step(step):
    if step.approver_user:
        return step.approver_user
    elif step.approver_group:
        return step.approver_group.user_set.first()  # 你可能需要一个更复杂的逻辑来选择组的审批人
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


# 这个是之前的老流程，通过点击审批不用了
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
        messages.error(request, '你没有权限删除此供应请求。')
    
    return redirect('approval_list')

@login_required
def approval_history(request):
    # 获取所有的供应请求
    supply_requests = SupplyRequest.objects.all().order_by('-created_at')
    
    # 为每个供应请求获取其审批历史和相关的办公用品项目
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

def send_approval_email(self, request):
    subject = f'审批请求: {self.supply_request.reason}'
    message = f"""
    请人: {self.supply_request.employee.username}
    申请原因: {self.supply_request.reason}

    点击以链接行审批:
    批准: {approve_url}
    拒绝: {reject_url}
    """
    
    email = EmailMessage(
        subject=force_bytes(subject).decode(),
        body=force_bytes(message).decode(),
        from_email=settings.EMAIL_HOST_USER,
        to=[self.approver.email],
    )
    
    try:
        email.send(fail_silently=False)
        self.email_sent_at = timezone.now()
        self.save()
    except Exception as e:
        logger.error(f"Failed to send approval email: {str(e)}")

@login_required
def email_approve(request, token, action):
    approval = get_object_or_404(RequestApproval, approval_token=token, status='pending')
    
    if action == 'approve':
        approval.status = 'approved'
        approval.is_approved = True
        messages.success(request, '申请已通件批准')
    elif action == 'reject':
        approval.status = 'rejected'
        messages.success(request, '申请已通过邮件拒绝')
    else:
        messages.error(request, '无效的操作')
        return redirect('home')
    
    approval.save()
    
    # 检查是否需要创建下一个审批步骤
    next_step = approval.step.get_next_step()
    if next_step:
        next_approval = RequestApproval.objects.create(
            supply_request=approval.supply_request,
            approver=next_step.approver_user,
            step=next_step,
            status='pending'
        )
        send_approval_email(request, next_approval)
    
    return redirect('home')

def reject_request(request, token):
    approval = get_object_or_404(RequestApproval, approval_token=token)
    if approval.status == 'pending':
        approval.status = 'rejected'
        approval.save()
        messages.success(request, '请求已被拒绝。')
    else:
        messages.error(request, '此请求已经被处理过了。')
    return redirect('some_appropriate_url_name')  # 替换为适当的URL名称

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
    approval_steps = ApprovalStep.objects.all().order_by('order')
    
    if request.method == 'POST':
        form = ApprovalStepForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, '审批步骤已添加')
            return redirect('approval_process_settings')
    else:
        form = ApprovalStepForm()
    
    return render(request, 'app01/approval_step_form.html', {
        'approval_steps': approval_steps,
        'form': form
    })

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
    
    return render(request, 'app01/approval_step_form.html', {
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

def send_approval_email(request, approval):
    subject = f'办公用品申请审批 - 申请编号 {approval.supply_request.id}'
    approve_url = request.build_absolute_uri(reverse('email_approve', args=[approval.approval_token, 'approve']))
    reject_url = request.build_absolute_uri(reverse('email_approve', args=[approval.approval_token, 'reject']))
    
    message = f"""
    您好，

    有一个新的办公用品申请需要您审批。

    申请人: {approval.supply_request.employee}
    申请原因: {approval.supply_request.reason}

    申请物品:
    {', '.join([f"{item.supply_option.name} ({item.quantity})" for item in approval.supply_request.items.all()])}

    请点击以下链接进行审批：
    同意: {approve_url}
    拒绝: {reject_url}

    或者，您可以登录系统进行更详细的审批操作。

    谢谢！
    """
    
    send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        [approval.approver.email],
        fail_silently=False,
    )

def email_approve(request, token, action):
    approval = get_object_or_404(RequestApproval, approval_token=token, status='pending')
    
    if action == 'approve':
        approval.status = 'approved'
        messages.success(request, '申请已通过邮件批准')
    elif action == 'reject':
        approval.status = 'rejected'
        messages.success(request, '申请已通过邮件拒绝')
    else:
        messages.error(request, '无效的操作')
        return redirect('home')
    
    approval.save()
    
    # 检查是否需要创建下一个审批步骤
    next_step = approval.step.get_next_step()
    if next_step:
        approvers = next_step.get_approvers()
        for approver in approvers:
            next_approval = RequestApproval.objects.create(
                supply_request=approval.supply_request,
                approver=approver,
                step=next_step,
                status='pending'
            )
            send_approval_email(request, next_approval)
    
    return redirect('home')

@login_required
def approve_request(request, approval_id):
    approval = get_object_or_404(RequestApproval, id=approval_id, approver=request.user, status='pending')
    
    if request.method == 'POST':
        action = request.POST.get('action')
        comment = request.POST.get('comment', '')
        
        if action == 'approve':
            approval.status = 'approved'
            messages.success(request, '申请已批准')
        elif action == 'reject':
            approval.status = 'rejected'
            messages.success(request, '申请已拒绝')
        else:
            messages.error(request, '无效的操作')
            return redirect('pending_approvals')
        
        approval.comment = comment
        approval.save()
        
        # 检查是否需要创建下一个审批步骤
        next_step = approval.step.get_next_step()
        if next_step:
            approvers = next_step.get_approvers()
            for approver in approvers:
                next_approval = RequestApproval.objects.create(
                    supply_request=approval.supply_request,
                    approver=approver,
                    step=next_step,
                    status='pending'
                )
                send_approval_email(request, next_approval)
        
        return redirect('pending_approvals')
    
    return render(request, 'app01/approve_request.html', {'approval': approval})

@login_required
def create_supply_request(request):
    if request.method == 'POST':
        form = SupplyRequestForm(request.POST)
        formset = OfficeSupplyItemFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            supply_request = form.save(commit=False)
            supply_request.employee = request.user
            supply_request.save()
            
            for item_form in formset:
                if item_form.cleaned_data:
                    item = item_form.save(commit=False)
                    item.supply_request = supply_request
                    item.save()
            
            # 创建第一个审批步骤
            first_step = ApprovalStep.objects.first()
            if first_step:
                approvers = first_step.get_approvers()
                for approver in approvers:
                    approval = RequestApproval.objects.create(
                        supply_request=supply_request,
                        approver=approver,
                        step=first_step,
                        status='pending'
                    )
                    send_approval_email(request, approval)
            
            messages.success(request, '申请已提交，等待审批')
            return redirect('supply_request_list')
    else:
        form = SupplyRequestForm()
        formset = OfficeSupplyItemFormSet()
    
    context = {
        'form': form,
        'formset': formset,
        'supply_options': OfficeSupplyOption.objects.all()
    }
    return render(request, 'app01/create_supply_request.html', context)










