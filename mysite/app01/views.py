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
from django.utils.encoding import force_str
from django.views.decorators.csrf import csrf_protect
from .models import RequestApproval, SupplyRequest, SupplyRequestItem# 注意这里使用 SupplyItem 而不是 RequestItem

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
def process_approval(request, approval_id, approve, comment):
    try:
        request_approval = RequestApproval.objects.get(id=approval_id)
    except RequestApproval.DoesNotExist:
        messages.error(request, "找不到对应的审批记录")
        return redirect('approval_error')

    supply_request = request_approval.supply_request
    current_step = request_approval.step

    # 检查供应请求的状态
    if supply_request.status == 'rejected':
        messages.warning(request, "该申请已被拒绝，无法进行进一步操作。")
        return redirect('approval_cancelled')

    if request_approval.status == 'cancelled':
        messages.warning(request, "该审批步骤已被取消，无法进行进一步操作。")
        return redirect('approval_cancelled')

    if request_approval.status != 'pending':
        messages.warning(request, "该审批已经被处理")
        return redirect('approval_already_processed')

    # 保存审批意见
    request_approval.comment = comment
    
    if approve:
        request_approval.status = 'approved'
        request_approval.save()

        # 检查当前步骤是否完成（所有未取消的审批都已赞成）
        all_approved = not RequestApproval.objects.filter(
            supply_request=supply_request,
            step=current_step,
            status__in=['pending', 'cancelled']
        ).exclude(status='approved').exists()

        if all_approved:
            # 当前步骤已完成，查找下一个步骤
            next_step = ApprovalStep.objects.filter(order__gt=current_step.order).order_by('order').first()
            
            if next_step:
                # 存在下一个步骤，创建新的审批记录
                supply_request.current_step = next_step
                supply_request.save()
                create_approval_records(supply_request, next_step)
            else:
                # 不存在下一个步骤，申请已全部批准
                supply_request.status = 'approved'
                supply_request.save()
                send_final_approval_email(supply_request)
            
            # 如果是会签，通知其他审批人该步骤已完成
            if current_step.is_countersign:
                pass
                # notify_other_approvers(supply_request, current_step, request_approval.approver)
        else:
            # 如果是会签，但还有其他人未审批，则通知申请人当前进度
            if current_step.is_countersign:
                pass
                # notify_requester_progress(supply_request, current_step)

        # 发送确认邮件给当前审批人
        # send_mail(
        #     '审批确认',
        #     f'您已成功批准了 {supply_request.requester} 的办公用品申请。',
        #     settings.DEFAULT_FROM_EMAIL,
        #     [request_approval.approver.email],
        #     fail_silently=False,
        # )
        messages.success(request, "审批成功")
        return redirect('approval_success')

    else:  # 拒绝
        request_approval.status = 'rejected'
        request_approval.save()

        # 无论是否为会签，只要有一人拒绝，整个申请就被拒绝
        supply_request.status = 'rejected'
        supply_request.save()

        # 将当前步骤的所有待处理审批都标记为已取消
        RequestApproval.objects.filter(
            supply_request=supply_request,
            step=current_step,
            status='pending'
        ).update(status='cancelled')

        # 发送拒绝邮件给申请人
        # send_mail(
        #     '办公用品申请被拒绝',
        #     f'您的办公用品申请已被 {request_approval.approver} 拒绝。',
        #     settings.DEFAULT_FROM_EMAIL,
        #     [supply_request.requester.email],
        #     fail_silently=False,
        # )

        # 发送确认邮件给当前审批人
        # send_mail(
        #     '审批确认',
        #     f'您已拒绝了 {supply_request.requester} 的办公用品申请。',
        #     settings.DEFAULT_FROM_EMAIL,
        #     [request_approval.approver.email],
        #     fail_silently=False,
        # )

        messages.success(request, "已拒绝申请")
        return redirect('approval_rejected')

    messages.error(request, "处理审批时出现错误")
    return redirect('approval_error')

def approve_request(request, approval_id):
    return process_approval(request, approval_id, approve=True)

def reject_request(request, approval_id):
    return process_approval(request, approval_id, approve=False)



def notify_requester_progress(supply_request, current_step):
    approved_count = RequestApproval.objects.filter(
        supply_request=supply_request,
        step=current_step,
        status='approved'
    ).count()

    total_count = RequestApproval.objects.filter(
        supply_request=supply_request,
        step=current_step
    ).count()

    send_mail(
        '审批进度更新',
        f'您的办公用品申请在当前步骤已获得 {approved_count}/{total_count} 的批准。',
        settings.DEFAULT_FROM_EMAIL,
        [supply_request.requester.email],
        fail_silently=False,
    )

def notify_other_approvers_of_rejection(supply_request, step, rejecting_approver):
    other_approvals = RequestApproval.objects.filter(
        supply_request=supply_request,
        step=step
    ).exclude(approver=rejecting_approver)

    for approval in other_approvals:
        send_mail(
            '申请已被其他审批人拒绝',
            f'{supply_request.requester} 的办公用品申请已被 {rejecting_approver} 拒绝，您无需进行进一步操作。',
            settings.DEFAULT_FROM_EMAIL,
            [approval.approver.email],
            fail_silently=False,
        )

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
    pending_approvals = RequestApproval.objects.filter(
        approver=request.user,
        status='pending'
    ).select_related(
        'supply_request__requester',
        'supply_request__current_step',
        'step'
    ).prefetch_related(
        Prefetch('supply_request__items', queryset=SupplyRequestItem.objects.all())
    ).order_by('supply_request__created_at')

    return render(request, 'app01/pending_approvals.html', {'pending_approvals': pending_approvals})


from django.core.mail import EmailMessage
from django.utils.encoding import force_bytes

# def send_approval_email(supply_request, approver):
#     current_approval = supply_request.get_current_approval()
#     approve_token = default_token_generator.make_token(approver)
#     uid = urlsafe_base64_encode(force_bytes(approver.pk))
    
#     approve_url = reverse('approve_request_email', kwargs={
#         'approval_id': current_approval.id,
#         'uidb64': uid,
#         'token': approve_token,
#         'action': 'approve'
#     })
#     reject_url = reverse('approve_request_email', kwargs={
#         'approval_id': current_approval.id,
#         'uidb64': uid,
#         'token': approve_token,
#         'action': 'reject'
#     })
    
#     site_url = settings.SITE_URL.rstrip('/')
#     approve_url = f"{site_url}{approve_url}"
#     reject_url = f"{site_url}{reject_url}"

#     print(f"Debug: SITE_URL = {settings.SITE_URL}")  # 调试信息
#     print(f"Debug: site_url = {site_url}")  # 调试信息
#     print(f"Debug: approve_url = {approve_url}")  # 调试信息
#     print(f"Debug: reject_url = {reject_url}")  # 调试信息

#     subject = f'办公用品申请审批 - 申请编号 {supply_request.id}'
#     message = f"""
#     您好 {approver.username}，

#     有一个新的办公用品申请需要您审批。

#     申请人: {supply_request.employee}
#     申请原因: {supply_request.reason}

#     申请物品:
#     {', '.join([f"{item.name} ({item.quantity})" for item in supply_request.items.all()])}

#     请点击以下链接进审批：
    
#     批: {approve_url}
    
#     拒绝: {reject_url}

#     或者您可以登录系统进行更详细的审批操作。

#     谢谢！
#     """
    
#     send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [approver.email], fail_silently=False)
#     print(f"Approval email sent to {approver.email}")  # 添加日志

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
    
    full_url = supply_request.build_absolute_uri(approve_url)
    print(full_url)

    site_url = settings.SITE_URL.rstrip('/')
    approve_url = f"{site_url}{approve_url}"
    reject_url = f"{site_url}{reject_url}"

    print(reject_url)
    print(approve_url)

    try:
        items = SupplyRequestItem.objects.filter(supply_request=supply_request)
        item_list = ",  ".join([f"- {item.office_supply}: {item.quantity}(个) " for item in items])
    except ObjectDoesNotExist:
        item_list = "无法获取物品列表"

    subject = f'办公用品申请审批 - 申编 {supply_request.id}'
    from_email = settings.DEFAULT_FROM_EMAIL
    recipient_list = [approver.email]
 
    if approver.email.endswith('njau.edu.cn') or approver.email.endswith('163.com'):
        # 163邮箱 写法
        html_message = '<p>您好 %s</p>' \
                '<p>有一个新的种子申请需要您审批。</p>' \
                '<p>申请人：%s </p>' \
                '<p>申请用途：%s</p>' \
                '<p>申请种子：%s</p>' \
                '<p>请点击以下链接进行审批：</p>' \
                '<p>批准：<a href="%s">%s</a></p>' \
                '<p>拒绝：<a href="%s">%s</a></p>' \
                '<p>或者您可以登录系统进行更详细的审批操作。</p><br>' \
                '<p>谢谢！</p><br>' %(approver.username, supply_request.requester, supply_request.purpose, item_list, approve_url,approve_url, reject_url,reject_url)
        send_mail(subject,'',settings.DEFAULT_FROM_EMAIL, recipient_list, html_message=html_message)
    else: 
        message = f"""
        您好 {approver.username}，

        有一个新的种子申请需要您审批。

        申请人: {supply_request.requester}
        申请用途: {supply_request.purpose}

        申请种子:
        {item_list}
        
        请点击以下链接进行审批：
        
        批准: {approve_url}
        
        拒绝: {reject_url}

        或者您可以登录系统进行更详细的审批操作。

        谢谢！
        """
        send_mail(subject, message, from_email, recipient_list, fail_silently=False)

   # '<p><a href="%s">%s<a></p>' % (approver.username, supply_request.requester, supply_request.purpose, item_list, approve_url, reject_url)
    # send_mail(subject,"", settings.DEFAULT_FROM_EMAIL, [self.approver.email], html_message=html_message)
    # msg='<a href="http://xxx" target="_blank">击激活</a>'
    # send_mail('注册激活','',settings.DEFAULT_FROM_EMAIL, ['t2024087@njau.edu.cn'], html_message=msg)

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


# @login_required
# def create_supply_request(request):
#     if request.method == 'POST':
#         form = SupplyRequestForm(request.POST)
#         formset = SupplyRequestItemFormSet(request.POST)
#         if form.is_valid() and formset.is_valid():
#             supply_request = form.save(commit=False)
#             supply_request.requester = request.user
#             supply_request.save()

#             for item_form in formset:
#                 if item_form.cleaned_data and not item_form.cleaned_data.get('DELETE', False):
#                     SupplyRequestItem.objects.create(
#                         supply_request=supply_request,
#                         office_supply=item_form.cleaned_data['office_supply'],
#                         quantity=item_form.cleaned_data['quantity']
#                     )
            
#             messages.success(request, '办公用品申请已成功提交。')
#             return redirect('supply_request_list')
#         else:
#             messages.error(request, '请检查表单中的错误。')
#     else:
#         form = SupplyRequestForm()
#         formset = SupplyRequestItemFormSet()
    
#     return render(request, 'create_supply_request.html', {'form': form, 'formset': formset})


@login_required
def create_supply_request(request):
    if request.method == 'POST':
        form = SupplyRequestForm(request.POST)
        formset = SupplyRequestItemFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
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
                
                # 获取第一个审批步骤
                first_step = ApprovalStep.objects.order_by('step_number').first()
                if first_step:
                    # 创建第一个步骤的审批记录并发送邮件
                    create_approval_records(supply_request, first_step)
                
                    # 更新供应请求的状态
                    supply_request.current_step = first_step
                    supply_request.status = 'pending'
                    supply_request.save()

            return redirect('supply_request_list')
    else:
        form = SupplyRequestForm()
        formset = SupplyRequestItemFormSet()
    
    return render(request, 'app01/create_supply_request.html', {'form': form, 'formset': formset})

def create_approval_records(supply_request, step):
    approvals_created = []

    if step.is_countersign:  # 会签情况
        approvers = step.get_approvers()
        for approver in approvers:
            approval = RequestApproval.objects.create(
                supply_request=supply_request,
                approver=approver,
                step=step,
                status='pending'
            )
            approvals_created.append(approval)
            send_approval_email(supply_request, approver)
    else:  # 非会签情况
        approver = step.get_approver()
        if approver:
            approval = RequestApproval.objects.create(
                supply_request=supply_request,
                approver=approver,
                step=step,
                status='pending'
            )
            approvals_created.append(approval)
            send_approval_email(supply_request, approver)

    return approvals_created










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

# region old code

# def process_email_approval(request, approval_id, uidb64, token, action):
#     """
#     处理通过邮件链接进行的审批操作。

#     参数:
#     request (HttpRequest): Django的请求对象
#     approval_id (int): 审批记录的ID
#     uidb64 (str): Base64编码的用户ID
#     token (str): 用于验证用户身份的令牌
#     action (str): 用户的操作，'approve' 或 'reject'

#     返回:
#     HttpResponse: 重定向到适当的页面（成功或错误页面）
#     """

#     # 解码用户ID并获取用户对象
#     try:
#         uid = urlsafe_base64_decode(uidb64).decode()
#         user = User.objects.get(pk=uid)
#     except (TypeError, ValueError, OverflowError, User.DoesNotExist):
#         user = None

#     # 验证用户身份和令牌有效性
#     if user is None or not default_token_generator.check_token(user, token):
#         messages.error(request, '无效或过期的审批链接')
        # return redirect('error_page')

#     # 获取审批记录
#     approval = get_object_or_404(RequestApproval, id=approval_id)

#     # 检查用户是否有权限进行审批
#     if approval.approver != user:
#         messages.error(request, '您没有权限进行此审批')
#         return redirect('error_page')

#     # 获取相应的申请对象
#     if approval.supply_request:
#         req_obj = approval.supply_request
#         request_type = 'supply'
#     elif approval.leave_request:
#         req_obj = approval.leave_request
#         request_type = 'leave'
#     else:
#         messages.error(request, '无的申请类型')
#         return redirect('error_page')

#     # 处理审批操作
#     if action == 'approve':
#         approval.status = 'approved'
#         messages.success(request, '您已批准此申请')
#     elif action == 'reject':
#         approval.status = 'rejected'
#         messages.success(request, '您已拒绝此申请')
#     else:
#         messages.error(request, '无的操作')
#         return redirect('error_page')

#     approval.save()

#     # 检查当前步骤的所有审批情况
#     current_step = approval.step
#     step_approvals = RequestApproval.objects.filter(step=current_step, **{f'{request_type}_request': req_obj})
    
#     all_approved = all(a.status == 'approved' for a in step_approvals)
#     any_rejected = any(a.status == 'rejected' for a in step_approvals)
#     all_processed = all(a.status != 'pending' for a in step_approvals)

#     if all_processed:
#         if current_step.is_countersign:
#             if all_approved:
#                 process_next_step(req_obj, current_step)
#             elif any_rejected:
#                 req_obj.status = 'rejected'
#                 req_obj.save()
#         else:
#             if any_rejected:
#                 req_obj.status = 'rejected'
#                 req_obj.save()
#             elif all_approved:
#                 process_next_step(req_obj, current_step)

#     return redirect('success_page')
# endregion

def process_email_approval(request, approval_id, uidb64, token , approve):
    try:
        # 如果 uidb64 已经是一个整数，直接使用它
        if isinstance(uidb64, int):
            uid = uidb64
        else:
            # 否则，尝试解码
            uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        messages.error(request, "无效的用户 ID")
        return redirect('approval_error')

    # 验证用户身份和令牌有效性
    if not default_token_generator.check_token(user, token):
        messages.error(request, "无效的令牌")
        return redirect('approval_error')

    # 获取特定的审批记录
    try:
        request_approval = RequestApproval.objects.get(id=approval_id, approver=user)
    except RequestApproval.DoesNotExist:
        messages.error(request, "找不到对应的审批记录")
        return redirect('approval_error')

    if request_approval.status != 'pending':
        messages.warning(request, "该审批已经被处理")
        return redirect('approval_already_processed')

    with transaction.atomic():
        supply_request = request_approval.supply_request
        current_step = request_approval.step

        # 检查当前申请是否已被取消
        if supply_request.status == 'rejected':
            messages.warning(request, "该申请已被拒绝，无法进行进一步操作。")
            return redirect('approval_cancelled')

        if request_approval.status == 'cancelled':
            messages.warning(request, "该审批步骤已被取消，无法进行进一步操作。")
            return redirect('approval_cancelled')

        if approve:
            request_approval.status = 'approved'
            request_approval.save()

            # 检查当前步骤是否完成（所有未取消的审批都已赞成）
            all_approved = not RequestApproval.objects.filter(
                supply_request=supply_request,
                step=current_step,
                status__in=['pending', 'cancelled']
            ).exclude(status='approved').exists()

            if all_approved:
                # 当前步骤已完成，查找下一个步骤
                next_step = ApprovalStep.objects.filter(step_number__gt=current_step.step_number).order_by('step_number').first()

                if next_step:
                    # 存在下一个步骤，创建新的审批记录
                    supply_request.current_step = next_step
                    supply_request.save()
                    create_approval_records(supply_request, next_step)
                else:
                    # 不存在下一个步骤，申请已全部批准
                    supply_request.status = 'approved'
                    supply_request.save()
                    send_final_approval_email(supply_request)
                
                # 如果是会签，通知其他审批人该步骤已完成
                if current_step.is_countersign:
                    pass
                    # notify_other_approvers(supply_request, current_step, request_approval.approver)
            else:
                # 如果是会签，但还有其他人未审批，则通知申请人当前进度
                if current_step.is_countersign:
                    pass
                    # notify_requester_progress(supply_request, current_step)

            # 发送确认邮件给当前审批人
            # send_mail(
            #     '审批确认',
            #     f'您已成功批准了 {supply_request.requester} 的办公用品申请。',
            #     settings.DEFAULT_FROM_EMAIL,
            #     [request_approval.approver.email],
            #     fail_silently=False,
            # )
            messages.success(request, "审批成功")
            return redirect('approval_success')

        else:  # 拒绝
            request_approval.status = 'rejected'
            request_approval.save()

            # 无论是否为会签，只要有一人拒绝，整个申请就被拒绝
            supply_request.status = 'rejected'
            supply_request.save()

            # 将当前步骤的所有待处理审批都标记为已取消
            RequestApproval.objects.filter(
                supply_request=supply_request,
                step=current_step,
                status='pending'
            ).update(status='cancelled')

            # 发送拒绝邮件给申请人
            # send_mail(
            #     '办公用品申请被拒绝',
            #     f'您的办公用品申请已被 {request_approval.approver} 拒绝。',
            #     settings.DEFAULT_FROM_EMAIL,
            #     [supply_request.requester.email],
            #     fail_silently=False,
            # )

            # 发送确认邮件给当前审批人
            # send_mail(
            #     '审批确认',
            #     f'您已拒绝了 {supply_request.requester} 的办公用品申请。',
            #     settings.DEFAULT_FROM_EMAIL,
            #     [request_approval.approver.email],
            #     fail_silently=False,
            # )
            messages.success(request, "已拒绝申请")
            return redirect('approval_rejected')

    messages.error(request, "处理审批时出现错误")
    return redirect('approval_error')

def send_final_approval_email(supply_request):
    # 发送最终批准邮件给申请人
    send_mail(
        '办公用品申请已批准',
        f'您的办公用品申请已被完全批准。',
        settings.DEFAULT_FROM_EMAIL,
        [supply_request.requester.email],
        fail_silently=False,
    )

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

# def create_approval_records(req_obj, step):
#     for approver in step.approvers.all():
#         RequestApproval.objects.create(
#             supply_request=req_obj if isinstance(req_obj, SupplyRequest) else None,
#             approver=approver,
#             step=step
#         )
#     # 这里可以添加发送审批邮件的逻辑

def approval_success(request):
    return render(request, 'app01/approval_success.html')

def approval_error(request):
    return render(request, 'app01/approval_error.html')





















































@require_POST
@csrf_protect
def add_approval_step(request):
    # 处理添加步骤的逻辑
    # ...
    return JsonResponse({'status': 'success', 'message': '步骤已添加'})

def approval_rejected(request):
    return render(request, 'app01/approval_rejected.html')

def approval_already_processed(request):
    return render(request, 'app01/approval_already_processed.html', {'message': '该审批已经被处理过，无法再次操作。'})

def approval_detail(request, approval_id):
    approval = get_object_or_404(RequestApproval, id=approval_id)
    
    if request.method == 'POST':
        action = request.POST.get('action')
        comment = request.POST.get('comment')
        
        if action in ['approve', 'reject']:
            return process_approval(request, approval_id, approve=(action == 'approve'), comment=comment)
    
    return render(request, 'app01/approval_detail.html', {'approval': approval})


