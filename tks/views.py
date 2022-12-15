
from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponseNotFound
from django.utils import timezone
from django.core import serializers
from django.views.decorators.cache import cache_control
from django.contrib import messages
from django.contrib.auth import login, logout, authenticate, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm, PasswordResetForm
from django.db import IntegrityError
from django.db.models import Q
from django.conf import settings
from django.core.mail import EmailMessage
from django.core.mail import send_mail, BadHeaderError
from django.template.loader import render_to_string
from django.db.models.query_utils import Q
from django.utils.encoding import force_bytes
from django.contrib.auth.tokens import default_token_generator
from django.contrib.sites.shortcuts import get_current_site
from django.core.files.base import ContentFile
from django.utils.http import urlsafe_base64_encode
from django.http import HttpResponse
from django.templatetags.static import static
from .models import *
from .forms import *
from datetime import datetime
import base64
import ast
import requests
import qrcode
import os



# Create your views here.
def index(request):
    if request.user.is_authenticated:
        if request.user.role == "STUDENT" or request.user.role == "FACULTY":
            return redirect("home_sf")
        elif request.user.role == "TOOL KEEPER":
            return redirect("transactions_tk")

    if request.method == "POST":
        login_form = LoginForm(request.POST)

        if login_form.is_valid():
            _username = login_form.cleaned_data.get("username")
            _password = login_form.cleaned_data.get("password")

            user = authenticate(request, username=_username, password=_password)

            if user is not None:
                login(request, user)
                if user.role == "STUDENT" or user.role == "FACULTY":
                    return redirect("home_sf")
                elif user.role == "TOOL KEEPER":
                    return redirect("transactions_tk")
            else:
                messages.add_message(request, messages.ERROR, "Username or password incorrect!")
                return redirect('/')
    else:
        login_form = LoginForm()

    context = {"login_form": login_form}
    return render(request, 'index.html', context)

def userlogout(request):
    logout(request)
    return redirect("index")

def registration_role(request):
    return render(request, "register_as.html")

def registration_student(request):
    if request.user.is_authenticated:
        if request.user.role == "STUDENT" or request.user.role == "FACULTY":
            return redirect(request, "home_sf.html")
        elif request.user.role == "TOOL KEEPER":
            return redirect(request, "home_tk.html")
    
    if request.method == "POST":
        registration_form = StudentRegistrationForm(request.POST)

        if registration_form.is_valid():
            new_user = registration_form
            new_user.save()
            messages.add_message(request, messages.SUCCESS, "Account created successfully!")
            return redirect('/')
        else:
            pass   
    else:
        registration_form = StudentRegistrationForm()

    context = {"registration_form": registration_form}
    return render(request, 'register_student.html', context)
    
def registration_faculty(request):
    if request.user.is_authenticated:
        if request.user.role == "FACULTY" or request.user.role == "STUDENT":
            return redirect(request, "sf/home_sf.html")
        elif request.user.role == "TOOL KEEPER":
            return redirect(request, "tk/home_tk.html")
    
    if request.method == "POST":
        registration_form = FacultyRegistrationForm(request.POST)

        if registration_form.is_valid():
            new_user = registration_form.save(commit=False)
            new_user.year_course = None
            new_user.save()
            messages.add_message(request, messages.SUCCESS, "Account created successfully!")
            return redirect('/')
        else:
            pass
    else:
        registration_form = FacultyRegistrationForm()

    context = {"registration_form": registration_form}
    return render(request, 'register_faculty.html', context)

def registration_toolkeeper(request):
    if request.user.is_authenticated:
        if request.user.role == "TOOL KEEPER":
            return redirect(request, "tk/home_tk.html")
        elif request.user.role == "FACULTY" or request.user.role == "STUDENT":
            return redirect(request, "sf/home_sf.html")
    
    if request.method == "POST":
        registration_form = ToolKeeperRegistrationForm(request.POST)

        if registration_form.is_valid():
            new_user = registration_form.save(commit=False)
            new_user.year_course = None
            new_user.save()
            messages.add_message(request, messages.SUCCESS, "Account created successfully!")
            return redirect('/')
        else:
            # Put something here when form is invalid...
            pass
    else:
        registration_form = ToolKeeperRegistrationForm()

    context = {"registration_form": registration_form}
    return render(request, 'register_toolkeeper.html', context)

@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@login_required(login_url='index')
def home_sf(request):
    tools = Tools.objects.filter(status="AVAILABLE")
    context = {'tools': tools}

    if request.user.is_authenticated:
        if request.user.role == "TOOL KEEPER":
            return redirect("transactions_tk")
    
    if request.user.has_ongoing_transaction == True:
        messages.add_message(request,
                messages.WARNING,
                "You have ongoing transaction. Void your reservation or return the tool/s you borrowed.",
                extra_tags="has_ongoing_transaction")
        return render(request, 'sf/home_sf.html', context)
        
    if request.method == "GET" and request.GET.get('storage') != None and request.GET.get('layer') != None:
        storage_num = int(request.GET.get('storage'))
        layer_num = int(request.GET.get('layer'))

        if storage_num != None:
            if layer_num != None:
                tools = Tools.objects.filter(storage=storage_num).filter(layer=layer_num).filter(status="AVAILABLE")
                context = {'tools': tools,
                            'storage': storage_num,
                            'layer': layer_num}
                return render(request, 'sf/home_sf.html', context)
             
            elif layer_num == None:
                tools = Tools.objects.filter(storage=storage_num).filter(status="AVAILABLE")
                context = {'tools': tools,
                            'storage': storage_num}
                return render(request, 'sf/home_sf.html', context)
        
    return render(request, 'sf/home_sf.html', context)

@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@login_required(login_url='index')
def reservation_sf(request):
    if request.user.is_authenticated:
        if request.user.role == "TOOL KEEPER":
            return redirect("transactions_tk")

    if request.method == "POST":
        ## Get all the tool ids in request.POST
        selected_tools = ast.literal_eval(request.POST.get('selected-tools-all'))

        ## Get the other values in request.POST
        borrow_date = request.POST.get('borrow-date')
        borrow_time = request.POST.get('borrow-time')
        return_date = request.POST.get('return-date')
        return_time = request.POST.get('return-time')

        ## Format date and time from the request.POST
        date_format = '%Y-%m-%d'
        time_format = '%H:%M'
        formatted_borrow_date = datetime.strptime(borrow_date, date_format).date()
        formatted_borrow_time = datetime.strptime(borrow_time, time_format).time()
        formatted_return_date = datetime.strptime(return_date, date_format).date()
        formatted_return_time = datetime.strptime(return_time, time_format).time()

        borrow_datetime = datetime.combine(formatted_borrow_date, formatted_borrow_time).astimezone()
        return_datetime = datetime.combine(formatted_return_date, formatted_return_time).astimezone()

        ## Save new transaction
        borrower = User.objects.get(pk=request.user.pk)
        borrower.has_ongoing_transaction = True
        borrower.save()

        new_transaction = Transactions.objects.create(
                tupc_id_id=borrower.pk,
                borrow_datetime=borrow_datetime,
                return_datetime=return_datetime,
                status="RESERVED")

        for item in selected_tools:
            tools = Tools.objects.get(pk=int(item))
            tools.current_user = borrower
            tools.current_transaction = new_transaction
            tools.status = "RESERVED"
            tools.save()

        # Generate QR code
        transaction_code = str(new_transaction.pk)

        # Creating an instance of qrcode
        qr = qrcode.QRCode(
                version=1,
                box_size=10,
                border=5)
        qr.add_data(transaction_code)
        qr.make(fit=True)
        qrcode_img = qr.make_image(fill='black', back_color='white')
        qrcode_img_file = f'{borrower.last_name+transaction_code[:2]+transaction_code[5:10]+transaction_code[-5:]}.png'
        qrcode_img.save(qrcode_img_file)
        new_transaction.qrcode = qrcode_img_file
        new_transaction.save()
       
        # Send email to user
        subject = "TKS Transaction Code"
        body = f"Greetings!\n\
                This is your QR Code for your transaction in TUP-C Tool Keeper System.\n\
                This will be used for borrowing and returning the tools you reserved.\n\
                Please keep in mind to save the QR Code to your device.\n\n\
                Thank You!"

        borrower_email = borrower.email
        email = EmailMessage(
            subject,
            body,
            settings.EMAIL_HOST_USER,
            [borrower_email],
            reply_to=[settings.EMAIL_HOST_USER],
            headers={'Message-ID': 'QRCODE'},
        )

        email.attach_file(qrcode_img_file)
        email.send()

        # Delete generated qrcode in the root directory
        os.remove(qrcode_img_file)

        return redirect('home_sf')

    if request.method == "GET":
        ## Get all the tool ids in request.GET
        selected_tools = request.GET.get('selected-tools-all').split(',')
        tools = []

        ## Verify the tool id status if it is available
        ## If not, void reservation
        for item in selected_tools:
            tool = Tools.objects.get(pk=int(item))
            if tool.status == "AVAILABLE":
                tools.append(tool.tool_name)
                ## --- Update tool status to 'RESERVED'
            elif tool.status != "NOT AVAILABLE":
                ### --- Pop up message that the user 
                ### - tool/s selected were not available
                ### --- Then return redirect to the home page
                
                return redirect('home_sf')
    
        context = {'tools': tools,
                'selected_tools_all': selected_tools}

        return render(request, 'sf/reservation_sf.html', context)

@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@login_required(login_url='index')
def profile_sf(request):
    if request.user.is_authenticated:
        if request.user.role == "TOOL KEEPER":
            return redirect("transactions_tk")

    if request.method == 'POST' and request.FILES.get('imageUpload') == None:
        form = EditUserForm(request.POST, instance=request.user)

        if form.is_valid():
            form.save()
            messages.add_message(request, messages.SUCCESS, "Account details updated successfully!", extra_tags="details_change_success")
            return redirect('profile_sf')
    
    if request.method == "POST" and request.FILES.get('imageUpload'):
        img = request.FILES.get('imageUpload')
        _user = User.objects.get(pk=request.user.pk)
        _user.user_img = img
        _user.save()
        messages.add_message(request, messages.SUCCESS, "Profile picture updated successfully!", extra_tags="img_change_success")

        return redirect('profile_sf')
    
    form = EditUserForm(instance=request.user)
        
    context = {
        'form': form,
    }

    return render(request, 'sf/profile_sf.html', context)


@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@login_required(login_url='index')
def change_password_sf(request, pk):
    if request.user.is_authenticated:
        if request.user.role == "TOOL KEEPER":
            return redirect("transactions_tk")

    if request.method == 'POST':
        form = PasswordChangeForm(user=request.user, data=request.POST)
        if form.is_valid():
            form.save()
            update_session_auth_hash(request, form.user)
            messages.add_message(request, messages.SUCCESS, "Password changed successfully!", extra_tags="pass_change_success")
            return redirect("profile_sf")
    
    else:
        form = PasswordChangeForm(user=request.user)
    
    context = {
        'form': form
    }
    
    return render(request, 'sf/change_password_sf.html', context)


@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@login_required(login_url='index')
def transactions_sf(request):
    if request.user.is_authenticated:
        if request.user.role == "TOOL KEEPER":
            return redirect("transactions_tk")
        

    user_transaction = Transactions.objects.filter(tupc_id_id=request.user.pk).order_by('-pk')
    context = {
        'transactions': user_transaction
    }

    return render(request, 'sf/transactions_sf.html', context)


@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@login_required(login_url='index')
def transaction_details_sf(request, transaction_id):
    if request.user.is_authenticated:
        transaction = Transactions.objects.get(pk=transaction_id)
        get_borrower = transaction.tupc_id_id
        if request.user.role == "TOOL KEEPER":
            return redirect("transactions_tk")
        if get_borrower != request.user.pk:
            return redirect("home_sf")

    if request.method == "POST":
        void_transaction = request.POST.get('void')
    ### --- Try catch errors next time. For the meantime...
        if void_transaction == "Yes, I'm sure":
            transaction = Transactions.objects.get(pk=transaction_id)
            borrower = User.objects.get(pk=request.user.pk)
            transaction.status = 'VOIDED'
            borrower.has_ongoing_transaction = False
            transaction.save()
            borrower.save()

            tools_borrowed = Tools.objects.filter(current_transaction_id=transaction.pk)
            for tool in tools_borrowed:
                tool.current_transaction = None
                tool.current_user = None
                tool.status = "AVAILABLE"
                TransactionDumps.objects.create(
                    transaction_id = transaction.pk,
                    tool_borrowed_id = tool.pk
                )
                tool.save()

            return redirect('transactions_sf')

    transaction_details = Transactions.objects.get(pk=transaction_id)
    tools_borrowed = Tools.objects.filter(current_transaction=transaction_id)
    dumps = TransactionDumps.objects.filter(transaction_id=str(transaction.pk))

    context = {
        'transaction_details': transaction_details,
        'tools': tools_borrowed,
        'dumps': dumps
    }

    return render(request, 'sf/transaction_details_sf.html', context)


@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@login_required(login_url='index')
def scanqr_tk(request):
    if request.user.is_authenticated:
        if request.user.role == "STUDENT" or request.user.role == "FACULTY":
            return redirect("home_sf")

    if request.method == "POST" and request.POST.get('qrcode'):
        qrcode = request.POST.get('qrcode')
        transaction = Transactions.objects.get(pk=qrcode)
        transaction_code = transaction.pk

        return redirect("transaction_details_tk", transaction_id=transaction_code)

    return render(request, 'tk/scanqr_tk.html')


@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@login_required(login_url='index') 
def transactions_tk(request):
    if request.user.is_authenticated:
        if request.user.role == "STUDENT" or request.user.role == "FACULTY":
            return redirect("home_sf")

    if request.method == "GET" and request.GET.get('filter') == "ALL":
        transactions = Transactions.objects.all().order_by('-pk')

    elif request.method == "GET" and request.GET.get('filter') == "RETURNED":
        transactions = Transactions.objects.filter(status="RETURNED").order_by('-pk')

    elif request.method == "GET" and request.GET.get('filter') == "BORROWED":
        transactions = Transactions.objects.filter(status="BORROWED").order_by('-pk')

    elif request.method == "GET" and request.GET.get('filter') == "RESERVED":
        transactions = Transactions.objects.filter(status="RESERVED").order_by('-pk')

    elif request.method == "GET" and request.GET.get('filter') == "VOIDED":
        transactions = Transactions.objects.filter(status="VOIDED").order_by('-pk')

    else:
        transactions = Transactions.objects.all().order_by('-pk')
        
    context = {'transactions': transactions}

    for i in range(len(transactions)):
        borrow_datetime_str = transactions[i].borrow_datetime.strftime("%b. %d, %Y, %I:%M %p")
        transactions[i].borrow_datetime = transactions[i].borrow_datetime.strptime(borrow_datetime_str, "%b. %d, %Y, %I:%M %p")
        return_datetime_str = transactions[i].return_datetime.strftime("%b. %d, %Y, %I:%M %p") 
        transactions[i].return_datetime = transactions[i].return_datetime.strptime(return_datetime_str, "%b. %d, %Y, %I:%M %p")
        
    return render(request, 'tk/transactions_tk.html', context)

#####################################
# View Transaction Details ToolKeeper
#####################################
@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@login_required(login_url='index')
def transaction_details_tk(request, transaction_id):
    transaction = Transactions.objects.get(pk=transaction_id)
    borrower = User.objects.get(tupc_id=transaction.tupc_id_id)
    tools_borrowed = Tools.objects.filter(current_transaction_id=transaction.pk)
    dumps = TransactionDumps.objects.filter(transaction_id=str(transaction.pk))
    context = {
        "borrower": borrower,
        "transaction": transaction,
        "tools_borrowed": tools_borrowed,
        "dumps": dumps
    }

    if request.user.is_authenticated:
        if request.user.role == "STUDENT" or request.user.role == "FACULTY":
            return redirect("home_sf")
            
    if request.method == "POST":
        if request.POST.get('option_btn') == "BORROW":
            storages = []
            # Open storage according where tools are located (send request.get in RPI)
            # Put rfid column in transaction table and scan rfid in tools
            for tool in tools_borrowed:
                storages.append(tool.storage)
                storages = list(dict.fromkeys(storages))
            
            context["storages"] = storages
            
            messages.add_message(request, messages.INFO, "SCAN THE RFID TAG ON THE TOOL", extra_tags="scan_rfid_borrow")
            return render(request, 'tk/transaction_details_tk.html', context)

        if request.POST.get('option_btn') == "VOID":
            transaction.status = "VOIDED"
            borrower.has_ongoing_transaction = False
            transaction.save()
            borrower.save()

            for tool in tools_borrowed:
                tool.current_transaction = None
                tool.current_user = None
                tool.status = "AVAILABLE"
                TransactionDumps.objects.create(
                    transaction_id = transaction.pk,
                    tool_borrowed_id = tool.pk
                )

                tool.save()

            return render(request, 'tk/transaction_details_tk.html', context)
   
        if request.POST.get('rfid_scanned') == "DONE":
            transaction.status = "BORROWED"
            for tools in tools_borrowed:
                tools.status = "BORROWED"
                tools.save()
            transaction.save()  
            return redirect ("transaction_details_tk", transaction_id)
        
        if request.POST.get('option_btn') == "RETURN":
            messages.add_message(request, messages.INFO, "SCAN THE RFID TAG ON THE TOOL TO VERIFY THE RETURN", extra_tags="scan_rfid_return")
            return redirect ("transaction_details_tk", transaction_id)

    return render(request, 'tk/transaction_details_tk.html', context)

def storages_tk(request):
    tools = Tools.objects.all()
    context =  {
        'tools': tools
    }

    return render(request, 'tk/manage_tools/storages_tk.html', context)

@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@login_required(login_url='index')
def add_tools_tk(request):
    if request.user.is_authenticated:
        if request.user.role == "STUDENT" or request.user.role == "FACULTY":
                return redirect("home_sf")

    if request.method == "POST":
        try:
            tool_id = request.POST.get('tool_id')
            tool_name = request.POST.get('tool_name')
            tool_image = request.POST.get('tool_img')
            storage = int(request.POST.get('storage'))
            layer = int(request.POST.get('layer'))

            # Modify base 64 image format to save in database
            format, imgstr = tool_image.split(';base64,')
            ext = format.split('/')[-1]
            data = ContentFile(base64.b64decode(imgstr))  
            file_name = tool_id + '.' + ext

            new_tool = Tools.objects.create(
                    tool_id = tool_id,
                    tool_name = tool_name,
                    storage = storage,
                    layer = layer,
                    status = "AVAILABLE"
            )

            new_tool.tool_image.save(file_name, data, save=True)
            new_tool.save()

            messages.add_message(request, messages.SUCCESS, "TOOL REGISTERED SUCCESSFULLY!")
            return redirect("add_tools_tk")
        
        except ValueError:
            messages.add_message(request, messages.ERROR, "NO TOOL IMAGE!", extra_tags="no_image_error")

        except IntegrityError:
            messages.add_message(request, messages.ERROR, "DUPLICATE ENTRY", extra_tags="duplicate_entry_error")

    return render(request, 'tk/manage_tools/add_tools_tk.html')

@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@login_required(login_url='index')
def tools_tk(request):
    if request.user.is_authenticated:
        if request.user.role == "STUDENT" or request.user.role == "FACULTY":
            return redirect("home_sf")

    if request.method == "GET" and request.GET.get('tool_id') != None:
        tool_id = int(request.GET.get('tool_id'))
        tool = Tools.objects.get(pk=tool_id)
        context =  {
            'tool': tool
        }
        return render(request, 'tk/manage_tools/tools_tk.html', context)
            
    return render(request, 'tk/manage_tools/tools_tk.html')

@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@login_required(login_url='index')
def profile_tk(request):
    if request.user.is_authenticated:
        if request.user.role == "STUDENT" or request.user.role == "FACULTY":
            return redirect("home_sf")

    if request.method == 'POST':
        form = EditUserForm(request.POST, instance=request.user)

        if form.is_valid():
            form.save()
            messages.add_message(request, messages.SUCCESS, "Account details has been updated!", extra_tags="details_change_success")
            return redirect('profile_tk')
    
    form = EditUserForm(instance=request.user)
        
    context = {
        'form': form,
    }

    return render(request, 'tk/profile_tk.html', context)


@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@login_required(login_url='index')
def change_password_tk(request, pk):
    if request.user.is_authenticated:
        if request.user.role == "STUDENT" or request.user.role == "FACULTY":
            return redirect("home_sf")

    if request.method == 'POST':
        form = PasswordChangeForm(user=request.user, data=request.POST)
        if form.is_valid():
            form.save()
            update_session_auth_hash(request, form.user)
            messages.add_message(request, messages.SUCCESS, "Password changed successfully!", extra_tags="pass_change_success")
            return redirect("profile_tk")
    
    else:
        form = PasswordChangeForm(user=request.user)
    
    context = {
        'form': form
    }
    
    return render(request, 'tk/change_password_tk.html', context)

# Reset Password
def reset_password(request):
    if request.method == 'POST':
        password_form = PasswordResetForm(request.POST)
        
        if password_form.is_valid():
            data = password_form.cleaned_data['email']
            user_email = User.objects.filter(Q(email=data))
            if user_email.exists():
                for user in user_email:
                    subject = 'Password Reset Request'
                    email_temp_name = 'password_reset/email_pass_message.txt'
                    current_site = get_current_site(request)
                    parameters = {
                        'email' : user.email,
                        'first_name' : user.first_name,
                        'username' : user.username,
                        'domain' : current_site.domain,
                        'uid' : urlsafe_base64_encode(force_bytes(user.pk)),
                        'token' : default_token_generator.make_token(user),
                        'protocol' : 'http', 
                    }

                    message = render_to_string(email_temp_name, parameters)

                    try:
                        send_mail(auth_user=settings.EMAIL_HOST_USER,
                                subject=subject,
                                message=message,
                                from_email='Tool Keeper TUPC',
                                recipient_list=[user.email],
                                fail_silently=False)

                        return redirect('reset_password_sent')
            
                    except BadHeaderError:
                        return HttpResponse('Invalid header found.')
       
            else:
                messages.add_message(request, messages.ERROR, "Use the registered email of your account.")
                return redirect('reset_password')

    else:
        password_form = PasswordResetForm()
        context = {'pf' : password_form}

    return render(request, 'password_reset/reset_password.html', context)

def openStorage(request):
    if request.method == "GET":
        # Receive data from ajax and ge the storage value
        storage = request.GET.get('storage')
        requests.get(f"http://192.168.0.111:5000/S{storage}")
        # Send request to RPI to open specific storage
        return JsonResponse({"message": f"Storage Opening {storage}"}, status=200)