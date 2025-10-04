from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Q
from django.utils import timezone
from .models import Company, CustomUser, Expense, ApprovalRule, ApprovalStep, ExpenseApproval
import requests
import pytesseract
from PIL import Image
from decimal import Decimal
import json
from datetime import datetime

def signup_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        company_name = request.POST.get('company_name')
        country = request.POST.get('country')
        currency = request.POST.get('currency')
        role = request.POST.get('role')

        # Validate role
        valid_roles = ['employee', 'manager', 'admin']
        if role not in valid_roles:
            messages.error(request, 'Invalid role selected.')
            return render(request, 'signup.html')

        # Duplicate check
        if CustomUser.objects.filter(username=username).exists():
            messages.error(request, f'Username "{username}" already exists. Choose a different one.')
            return render(request, 'signup.html')

        # Create company
        company = Company.objects.create(
            name=company_name,
            country=country,
            currency=currency
        )

        # Create user with selected role
        user = CustomUser.objects.create_user(
            username=username,
            email=email,
            password=password,
            company=company,
            role=role  # Use the role from the form
        )

        # Log in the user
        login(request, user)
        messages.success(request, 'Account created successfully!')

        # Redirect based on role
        if role == 'admin':
            return redirect('admin_dashboard')
        elif role == 'manager':
            return redirect('manager_dashboard')
        else:
            return redirect('employee_dashboard')

    return render(request, 'signup.html')
def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        
        if user:
            login(request, user)
            return redirect('dashboard')
        else:
            messages.error(request, 'Invalid credentials')
    
    return render(request, 'login.html')

@login_required
def logout_view(request):
    logout(request)
    return redirect('login')

@login_required
def dashboard_view(request):
    if request.user.role == 'admin':
        return redirect('admin_dashboard')
    elif request.user.role == 'manager':
        return redirect('manager_dashboard')
    else:
        return redirect('employee_dashboard')

@login_required
def admin_dashboard(request):
    if request.user.role != 'admin':
        messages.error(request, 'Access denied')
        return redirect('dashboard')
    
    employees = CustomUser.objects.filter(company=request.user.company).exclude(id=request.user.id)
    approval_rules = ApprovalRule.objects.filter(company=request.user.company)
    expenses = Expense.objects.filter(company=request.user.company)[:10]
    
    context = {
        'employees': employees,
        'approval_rules': approval_rules,
        'expenses': expenses,
    }
    return render(request, 'admin_dashboard.html', context)

@login_required
def manager_dashboard(request):
    if request.user.role not in ['manager', 'admin']:
        messages.error(request, 'Access denied')
        return redirect('dashboard')
    
    pending_approvals = ExpenseApproval.objects.filter(
        approver=request.user,
        status='pending'
    )
    
    team_expenses = Expense.objects.filter(
        employee__manager=request.user
    ) if request.user.role == 'manager' else Expense.objects.filter(company=request.user.company)
    
    context = {
        'pending_approvals': pending_approvals,
        'team_expenses': team_expenses[:10],
    }
    return render(request, 'manager_dashboard.html', context)

@login_required
def employee_dashboard(request):
    my_expenses = Expense.objects.filter(employee=request.user)
    
    context = {
        'my_expenses': my_expenses,
    }
    return render(request, 'employee_dashboard.html', context)

@login_required
def create_employee(request):
    if request.user.role != 'admin':
        return JsonResponse({'error': 'Access denied'}, status=403)
    
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        role = request.POST.get('role')
        manager_id = request.POST.get('manager_id')

        # Duplicate username check
        if CustomUser.objects.filter(username=username).exists():
            messages.error(request, f'Username "{username}" already exists. Choose a different one.')
            return redirect('create_employee')  # redirect to form
        
        manager = None
        if manager_id:
            manager = CustomUser.objects.get(id=manager_id)
        
        # Safe user creation
        user = CustomUser.objects.create_user(
            username=username,
            email=email,
            password=password,
            company=request.user.company,
            role=role,
            manager=manager
        )
        
        messages.success(request, f'User {username} created successfully')
        return redirect('admin_dashboard')
    
    managers = CustomUser.objects.filter(company=request.user.company, role='manager')
    return render(request, 'create_employee.html', {'managers': managers})


@login_required
def submit_expense(request):
    if not request.user.company:
        messages.error(request, '❌ You are not assigned to any company.')
        return redirect('dashboard')

    if request.method == 'POST':
        amount = request.POST.get('amount')
        currency = request.POST.get('currency')
        category = request.POST.get('category')
        description = request.POST.get('description')
        merchant_name = request.POST.get('merchant_name', '')
        expense_date = request.POST.get('expense_date')
        receipt_image = request.FILES.get('receipt_image')

        company_currency = request.user.company.currency
        amount_in_company_currency = convert_currency(float(amount), currency, company_currency)

        # Expense created as pending
        expense = Expense.objects.create(
            employee=request.user,
            company=request.user.company,
            amount=amount,
            currency=currency,
            amount_in_company_currency=amount_in_company_currency,
            category=category,
            description=description,
            merchant_name=merchant_name,
            expense_date=expense_date,
            receipt_image=receipt_image,
            status='pending',  # always pending initially
            current_step=0
        )

        # Create approval workflow (manager/admin)
        create_approval_workflow(expense)

        messages.success(request, '✅ Expense submitted successfully and is now pending approval.')
        return redirect('employee_dashboard')

    return render(request, 'submit_expense.html')




@login_required
def ocr_scan(request):
    if request.method == 'POST' and request.FILES.get('receipt'):
        try:
            receipt = request.FILES['receipt']
            image = Image.open(receipt)
            text = pytesseract.image_to_string(image)
            
            expense_data = parse_receipt_text(text)
            return JsonResponse(expense_data)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    
    return JsonResponse({'error': 'No receipt provided'}, status=400)

@login_required
def approve_expense(request, expense_id):
    if request.user.role not in ['manager', 'admin']:
        messages.error(request, 'Access denied')
        return redirect('dashboard')
    
    expense = get_object_or_404(Expense, id=expense_id)
    approval = ExpenseApproval.objects.filter(
        expense=expense,
        approver=request.user,
        status='pending'
    ).first()
    
    if not approval:
        messages.error(request, 'No pending approval found')
        return redirect('manager_dashboard')
    
    if expense.approval_rule and expense.approval_rule.rule_type == 'sequential':
        previous_approvals = ExpenseApproval.objects.filter(
            expense=expense,
            step_number__lt=approval.step_number
        )
        if previous_approvals.exclude(status='approved').exists():
            messages.error(request, 'All previous approval steps must be approved first')
            return redirect('manager_dashboard')
    
    if request.method == 'POST':
        action = request.POST.get('action')
        comments = request.POST.get('comments', '')
        
        if action == 'approve':
            approval.status = 'approved'
            approval.comments = comments
            approval.save()
            
            process_approval_workflow(expense)
            messages.success(request, 'Expense approved')
        elif action == 'reject':
            approval.status = 'rejected'
            approval.comments = comments
            approval.save()
            
            expense.status = 'rejected'
            expense.save()
            messages.success(request, 'Expense rejected')
        
        return redirect('manager_dashboard')
    
    context = {
        'expense': expense,
        'approval': approval,
    }
    return render(request, 'approve_expense.html', context)

@login_required
def create_approval_rule(request):
    if request.user.role != 'admin':
        messages.error(request, 'Access denied')
        return redirect('dashboard')
    
    if request.method == 'POST':
        name = request.POST.get('name')
        rule_type = request.POST.get('rule_type')
        percentage_threshold = request.POST.get('percentage_threshold')
        specific_approver_id = request.POST.get('specific_approver_id')
        is_manager_first = request.POST.get('is_manager_first') == 'on'
        
        rule = ApprovalRule.objects.create(
            company=request.user.company,
            name=name,
            rule_type=rule_type,
            percentage_threshold=int(percentage_threshold) if percentage_threshold else None,
            specific_approver_id=specific_approver_id if specific_approver_id else None,
            is_manager_first=is_manager_first
        )
        
        approver_ids = request.POST.getlist('approvers[]')
        for idx, approver_id in enumerate(approver_ids, start=1):
            ApprovalStep.objects.create(
                approval_rule=rule,
                approver_id=approver_id,
                sequence=idx
            )
        
        messages.success(request, 'Approval rule created successfully')
        return redirect('admin_dashboard')
    
    employees = CustomUser.objects.filter(company=request.user.company, role__in=['manager', 'admin'])
    return render(request, 'create_approval_rule.html', {'employees': employees})

@login_required
def get_countries(request):
    try:
        response = requests.get('https://restcountries.com/v3.1/all?fields=name,currencies')
        return JsonResponse(response.json(), safe=False)
    except:
        return JsonResponse({'error': 'Could not fetch countries'}, status=500)

def convert_currency(amount, from_currency, to_currency):
    if from_currency == to_currency:
        return Decimal(amount)
    
    try:
        response = requests.get(f'https://api.exchangerate-api.com/v4/latest/{from_currency}')
        data = response.json()
        rate = data['rates'].get(to_currency, 1)
        return Decimal(amount) * Decimal(str(rate))
    except:
        return Decimal(amount)

def create_approval_workflow(expense):
    rules = ApprovalRule.objects.filter(company=expense.company, is_active=True).first()
    
    if not rules:
        expense.status = 'approved'
        expense.save()
        return
    
    expense.approval_rule = rules
    expense.save()
    
    step_number = 1
    
    if rules.is_manager_first and expense.employee.manager:
        ExpenseApproval.objects.create(
            expense=expense,
            approver=expense.employee.manager,
            step_number=step_number,
            status='pending'
        )
        step_number += 1
    
    for step in rules.steps.all():
        ExpenseApproval.objects.create(
            expense=expense,
            approver=step.approver,
            step_number=step_number,
            status='pending'
        )
        step_number += 1

def process_approval_workflow(expense):
    rule = expense.approval_rule
    
    if not rule:
        expense.status = 'approved'
        expense.save()
        return
    
    current_approvals = ExpenseApproval.objects.filter(expense=expense, status='approved')
    total_approvals = ExpenseApproval.objects.filter(expense=expense).count()
    
    if rule.rule_type == 'sequential':
        all_approvals = ExpenseApproval.objects.filter(expense=expense).order_by('step_number')
        for approval in all_approvals:
            if approval.status == 'pending':
                return
            elif approval.status == 'rejected':
                expense.status = 'rejected'
                expense.save()
                return
        expense.status = 'approved'
        expense.save()
        return
    
    if rule.rule_type == 'specific' and rule.specific_approver:
        if current_approvals.filter(approver=rule.specific_approver).exists():
            expense.status = 'approved'
            expense.save()
            return
    
    if rule.rule_type == 'percentage' and rule.percentage_threshold:
        approval_percentage = (current_approvals.count() / total_approvals) * 100
        if approval_percentage >= rule.percentage_threshold:
            expense.status = 'approved'
            expense.save()
            return
    
    if rule.rule_type == 'hybrid':
        if rule.specific_approver and current_approvals.filter(approver=rule.specific_approver).exists():
            expense.status = 'approved'
            expense.save()
            return
        
        if rule.percentage_threshold:
            approval_percentage = (current_approvals.count() / total_approvals) * 100
            if approval_percentage >= rule.percentage_threshold:
                expense.status = 'approved'
                expense.save()
                return
    
    pending_approvals = ExpenseApproval.objects.filter(expense=expense, status='pending')
    if not pending_approvals.exists():
        if current_approvals.count() == total_approvals:
            expense.status = 'approved'
            expense.save()

def parse_receipt_text(text):
    import re
    
    data = {
        'amount': '',
        'date': '',
        'merchant_name': '',
        'description': text[:200]
    }
    
    amount_pattern = r'\$?\s*(\d+\.?\d*)'
    amounts = re.findall(amount_pattern, text)
    if amounts:
        data['amount'] = amounts[-1]
    
    date_pattern = r'(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})'
    dates = re.findall(date_pattern, text)
    if dates:
        data['date'] = dates[0]
    
    lines = text.split('\n')
    if lines:
        data['merchant_name'] = lines[0].strip()
    
    return data
