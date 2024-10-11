

def get_approvers(employee):
    approvers = []
    if employee.profile.direct_manager:
        approvers.append((employee.profile.direct_manager, 1))
    if employee.profile.department and employee.profile.department.head:
        approvers.append((employee.profile.department.head, 2))
    # 可以添加更多的逻辑来确定其他审批人
    return approvers