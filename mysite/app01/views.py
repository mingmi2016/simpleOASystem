from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from .models import ApprovalStep, SupplyRequest, SupplyRequestItem
from .forms import SupplyRequestForm, SupplyRequestItemFormSet, RequestApprovalForm
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
from django.db import models
from django.forms import inlineformset_factory

logger = logging.getLogger(__name__)



#  views.py 中使用这个函数
from .utils import get_approvers


from django.shortcuts import render


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
def approve_request(request, request_id):
    req = get_object_or_404(Request, id=request_id)
    current_step = req.current_step
    
    if request.method == 'POST':
        is_approved = request.POST.get('decision') == 'approve'
        comment = request.POST.get('comment', '')
        
        # 创建或更新审批记录
        approval, created = RequestApproval.objects.update_or_create(
            request=req,
            step=current_step,
            approver=request.user,
            defaults={'is_approved': is_approved, 'comment': comment}
        )
        
        # 检查是否所有必要的审批人都已做出决定
        step_approvals = RequestApproval.objects.filter(request=req, step=current_step)
        all_approved = True
        all_decided = step_approvals.count() == current_step.approvers.count()
        
        if current_step.is_countersign:
            # 会签逻辑
            if all_decided:
                all_approved = all(approval.is_approved for approval in step_approvals)
        else:
            # 非会签逻（任一人批准即可）
            all_approved = any(approval.is_approved for approval in step_approvals)
        
        if all_decided:
            if all_approved:
                # 移至下一步或完成审
                next_step = ApprovalStep.objects.filter(
                    process_name=current_step.process_name,
                    step_number__gt=current_step.step_number
                ).order_by('step_number').first()
                
                if next_step:
                    req.current_step = next_step
                else:
                    req.status = 'approved'
            else:
                req.status = 'rejected'
            
            req.save()
        
        return redirect('request_detail', request_id=req.id)
    
    context = {
        'request': req,
        'current_step': current_step,
    }
    return render(request, 'app01/approve_request.html', context)

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
    supply_requests = SupplyRequest.objects.all().order_by('-created_at')
    for supply_request in supply_requests:
        # 不要直接赋值，而是在模板中使用反向关系
        supply_request.items_list = supply_request.items.all()
    return render(request, 'app01/supply_request_list.html', {'supply_requests': supply_requests})

@login_required
def approval_list(request):
    print(f"Current user: {request.user}")
    pending_approvals = RequestApproval.objects.filter(approver=request.user, is_approved=None)
    print(f"Pending approvals: {pending_approvals.count()}")
    for approval in pending_approvals:
        print(f"Approval ID: {approval.id}, Supply Request: {approval.supply_request}, Step: {approval.step}")
    return render(request, 'app01/approval_list.html', {'pending_approvals': pending_approvals})




from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from .models import ApprovalStep
from .forms import ApprovalStepForm

def is_admin(user):
    return user.is_superuser or user.is_staff

@login_required
@user_passes_test(is_admin)
def approval_step_list(request):
    steps = ApprovalStep.objects.all().order_by('step_number')
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
    supply_requests = SupplyRequest.objects.all().order_by('-created_at')
    
    requests_data = []
    for supply_request in supply_requests:
        items = SupplyRequestItem.objects.filter(supply_request=supply_request)
        approvals = RequestApproval.objects.filter(supply_request=supply_request).order_by('created_at')
        
        requests_data.append({
            'request': supply_request,
            'items': items,
            'approvals': approvals,
        })
    
    return render(request, 'app01/approval_history.html', {'requests_data': requests_data})

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

    请点击以下链接进审批：
    
    批: {approve_url}
    
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
            messages.error(request, '无效的操')
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
    if request.method == 'POST':
        form = ApprovalStepForm(request.POST)
        if form.is_valid():
            approval_step = form.save(commit=False)
            max_order = ApprovalStep.objects.aggregate(models.Max('order'))['order__max'] or 0
            approval_step.order = max_order + 1
            approval_step.save()
            form.save_m2m()
            return redirect('approval_process_settings')
    else:
        form = ApprovalStepForm()

    # 按 process_name 和 order 排序
    approval_steps = ApprovalStep.objects.all().order_by('process_name', 'order')
    
    return render(request, 'app01/approval_process_settings.html', {
        'form': form, 
        'approval_steps': approval_steps
    })

@login_required
def edit_approval_step(request, step_id):
    step = get_object_or_404(ApprovalStep, id=step_id)
    if request.method == 'POST':
        form = ApprovalStepForm(request.POST, instance=step)
        if form.is_valid():
            form.save()
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





def send_approval_email(supply_request, approver):
    # 生成审链接
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

    subject = f'办公用品申请审批 - 申编 {supply_request.id}'
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
            messages.success(request, '申请已准')
        elif action == 'reject':
            approval.status = 'rejected'
            approval.save()
            approval.supply_request.status = 'rejected'
            approval.supply_request.save()
            messages.success(request, '申请已绝')
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
        formset = SupplyRequestItemFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            supply_request = form.save(commit=False)
            supply_request.requester = request.user
            supply_request.save()

            for item_form in formset:
                if item_form.cleaned_data and not item_form.cleaned_data.get('DELETE', False):
                    SupplyRequestItem.objects.create(
                        supply_request=supply_request,
                        office_supply=item_form.cleaned_data['office_supply'],
                        quantity=item_form.cleaned_data['quantity']
                    )
            
            messages.success(request, '办公用品申请已成功提交。')
            return redirect('supply_request_list')
        else:
            messages.error(request, '请检查表单中的错误。')
    else:
        form = SupplyRequestForm()
        formset = SupplyRequestItemFormSet()
    
    return render(request, 'create_supply_request.html', {'form': form, 'formset': formset})










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

def process_email_approval(request, approval_id, uidb64, token, action):
    """
    处理通过邮件链接进行的审批操作。

    参数:
    request (HttpRequest): Django的请求对象
    approval_id (int): 审批记录的ID
    uidb64 (str): Base64编码的用户ID
    token (str): 用于验证用户身份的令牌
    action (str): 用户的操作，'approve' 或 'reject'

    返回:
    HttpResponse: 重定向到适当的页面（成功或错误页面）
    """

    # 解码用户ID并获取用户对象
    try:
        uid = urlsafe_base64_decode(uidb64).decode()
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    # 验证用户身份和令牌有效性
    if user is None or not default_token_generator.check_token(user, token):
        messages.error(request, '无效或过期的审批链接')
        return redirect('error_page')

    # 获取审批记录
    approval = get_object_or_404(RequestApproval, id=approval_id)

    # 检查用户是否有权限进行审批
    if approval.approver != user:
        messages.error(request, '您没有权限进行此审批')
        return redirect('error_page')

    # 获取相应的申请对象
    if approval.supply_request:
        req_obj = approval.supply_request
        request_type = 'supply'
    elif approval.leave_request:
        req_obj = approval.leave_request
        request_type = 'leave'
    else:
        messages.error(request, '无的申请类型')
        return redirect('error_page')

    # 处理审批操作
    if action == 'approve':
        approval.status = 'approved'
        messages.success(request, '您已批准此申请')
    elif action == 'reject':
        approval.status = 'rejected'
        messages.success(request, '您已拒绝此申请')
    else:
        messages.error(request, '无的操作')
        return redirect('error_page')

    approval.save()

    # 检查当前步骤的所有审批情况
    current_step = approval.step
    step_approvals = RequestApproval.objects.filter(step=current_step, **{f'{request_type}_request': req_obj})
    
    all_approved = all(a.status == 'approved' for a in step_approvals)
    any_rejected = any(a.status == 'rejected' for a in step_approvals)
    all_processed = all(a.status != 'pending' for a in step_approvals)

    if all_processed:
        if current_step.is_countersign:
            if all_approved:
                process_next_step(req_obj, current_step)
            elif any_rejected:
                req_obj.status = 'rejected'
                req_obj.save()
        else:
            if any_rejected:
                req_obj.status = 'rejected'
                req_obj.save()
            elif all_approved:
                process_next_step(req_obj, current_step)

    return redirect('success_page')

def process_next_step(req_obj, current_step):
    next_step = ApprovalStep.objects.filter(
        process_name=current_step.process_name,
        step_number=current_step.step_number + 1
    ).first()

    if next_step:
        req_obj.current_step += 1
        req_obj.save()
        create_approval_records(req_obj, next_step)
    else:
        req_obj.status = 'approved'
        req_obj.save()

def create_approval_records(req_obj, step):
    for approver in step.approvers.all():
        RequestApproval.objects.create(
            supply_request=req_obj if isinstance(req_obj, SupplyRequest) else None,
            leave_request=req_obj if isinstance(req_obj, LeaveRequest) else None,
            approver=approver,
            step=step
        )
    # 这里可以添加发送审批邮件的逻辑

def approval_success(request):
    return render(request, 'app01/approval_success.html')

def approval_error(request):
    return render(request, 'app01/approval_error.html')














































