from django.shortcuts import render
import logging
from rest_framework.views import APIView
from ldap3 import Server, Connection, ALL, SUBTREE

import json, requests
from rest_framework.authtoken.models import Token
from rest_framework.response import Response
from rest_framework import status
from django.core import signing
import sys
import smtplib
from rest_framework import generics, permissions
from .models import *
from django.contrib.auth import get_user_model
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

User = get_user_model()

# Create your views here.



## actual code to send email
def send_mail(sender, receiver, message):
    logging.info("Inside send mail")
    sender = sender
    receivers = [receiver]
    # receivers = 'divyansh.nishad@airtel.com'
    message = message
    smtpObj = smtplib.SMTP("10.56.131.8")
    smtpObj.sendmail(sender, receivers, message)
    logging.info("SMTP send mail")
    print("SMTP send mail")
    print(f"Successfully sent email  to {receiver}")


## sending the approval request email to user's rm for Approval ( Level 1 Approval)
def send_approval_email_to_user_rm(id):
    logging.info("Inside function to send mail to rm")
    print("Inside function to send mail to rm")
    request_instance = DCTSignupRequest.objects.get(id=id)
    reporting_manager_email = request_instance.reporting_manager_email
    message = f"""From: MOP Tool Signup Request <mop_tool_automation@airtel.com>
To: To Person <{reporting_manager_email}>
Subject: MOP Tool Signup Request

User's Name - {request_instance.name}
User's OLMID - {request_instance.olmid}
User Type - {request_instance.user_type}

Click on the below Links to approve or reject the request.
http://10.227.244.108:10019/mailapproval-rm/{signing.dumps(id)}/
"""
    logging.info("sending mail to mop tool automation")
    print("sending mail to mop tool automation")
    send_mail("mop_tool_automation@airtel.com", reporting_manager_email, message)


## sending the approval request email to l2 for approval ( Level 2 Approval)
# User Type - {request_instance.user_type}
def send_approval_email_to_vertical_head(id):
    request_instance = DCTSignupRequest.objects.get(id=id)
    vertical_head_email = request_instance.vertical_head_email
    message = f"""From: DCT Tool Signup Request <mop_tool_automation@airtel.com>
To: To Person <{vertical_head_email}>
Subject: DCT Tool Signup Request

User's Name - {request_instance.name}
User's OLMID - {request_instance.olmid}

Click on the below Link to approve or reject the request.
Approval link - http://10.8.147.12:8525/mailapproval-vh/{signing.dumps(id)}/
"""
    send_mail("mop_tool_automation@airtel.com", vertical_head_email, message)


## sending the lab credentials to user after approval
def send_credentials_email_to_user(id, password):
    print(password)
    request_instance = DCTSignupRequest.objects.get(id=id)
    user_email = request_instance.user_email
    username = request_instance.olmid
    message = f"""From: MIS Tool Signup Request <mop_tool_automation@airtel.com>
To: To Person <{user_email}>
Subject: MIS Tool Signup Request

Your MIS Tool Signup request was approved. You can use the following credentials to log in.
Username - {username}
Password - {password}

Portal URL : http://10.8.147.12:8525/
"""
    send_mail("mop_tool_automation@airtel.com", user_email, message)


## sending the lab request rejection mail to user
def send_rejection_email_to_user(id, rejected_by):
    request_instance = DCTSignupRequest.objects.get(id=id)
    user_email = request_instance.user_email
    message = f"""From: MOP Tool Signup Request <mop_tool_automation@airtel.com>
To: To Person <{user_email}>
Subject: MOP Tool Signup Request Rejected

Your MOP Tool Signup Request was rejected by {rejected_by}.
"""
    send_mail("mop_tool_automation@airtel.com", user_email, message)


##### register
class CreateUserView(APIView):
    def post(self, request, *args, **kwargs):
        try:

            username = request.data.get("username")
            email = request.data.get("email")
            # is_staff=request.data.get('is_staff')
            # team=request.data.get('team')
            password = request.data.get("password")

            user, created = User.objects.get_or_create(
                username=username, email=email, password=password
            )  # team = team

            logging.info(f"User:{user},Created:{created}")

            if created:
                return Response(
                    {"message": "Signup Successful."}, status=status.HTTP_201_CREATED
                )

            return Response(
                {"error": "A user with this username already exist."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        except Exception as e:
            print(e)
            logging.info(f"Error In CreateUserView:{e}")
            exc_type, exc_obj, exc_tb = sys.exc_info()
            print(
                f"There was an error processing your request.Exception line:{exc_tb.tb_lineno},Error:{e}"
            )
            return Response(
                {"error": "There was some error."}, status=status.HTTP_401_UNAUTHORIZED
            )


def check_ldap_api(username, password):
    """
    Check LDAP API with credentials and return True if status code is 200, else False.
    Args:
        username (str): API username
        password (str): API password
    Returns:
        bool: True if successful (200), False otherwise
    """
    url = "http://10.227.244.107:9006/labapi/personaldap/"
    payload = {
        "username": username,
        "password": password
    }
    files = []
    headers = {}
    response = requests.post(url, headers=headers, data=payload, files=files)
    return response.status_code == 200

#### login
class LoginView(APIView):
    # renderer_classes = api_settings.DEFAULT_RENDERER_CLASSES

    def post(self, request, *args, **kwargs):

        try:

            username = request.data.get("username")

            try:
                user = User.objects.get(username=username)
            except User.DoesNotExist:
                return Response(
                    {
                        "Error": "You are not authorized to login.Please create and get your account approved before logging in."
                    },
                    status=status.HTTP_401_UNAUTHORIZED,
                )

            password = request.data.get("password")

            ldap_result = check_ldap_api(username, password)

            # print(username,password)

            # ldap_server = "10.5.112.202"

            # bind_dn = f"{username}@india.airtel.itm"

            # base_dn = "dc=india,dc=airtel,dc=itm"

            # samaccountname = f"{username}"

            # server = Server(ldap_server, get_info=ALL)

            # conn = Connection(server, bind_dn, password, auto_bind=True)

            # search_filter = f"(&(objectClass=user)(sAMAccountName={samaccountname}))"

            # conn.search(
            #     search_base=base_dn,
            #     search_filter=search_filter,
            #     search_scope=SUBTREE,
            #     attributes=[
            #         "sAMAccountName",
            #         "manager1",
            #         "supervisorMail",
            #         "name",
            #         "mail",
            #         "memberOf",
            #         "subFunction",
            #         "subSubFunction",
            #         "department",
            #     ],
            # )

            # results = conn.entries

            # entry_json = results[0].entry_to_json()

            # entry_dict = json.loads(entry_json)

            # department = entry_dict["attributes"]["department"][0]



            # print(f"User is from {department}")

            # if not department == 'Network-NOC':
            #     return Response({"error": "User Outside NOC"}, status=status.HTTP_203_NON_AUTHORITATIVE_INFORMATION)
            # print(entry_dict)
            if ldap_result:

                token, _ = Token.objects.get_or_create(user=user)
                return Response(
                    {
                        "token": str(token.key),
                        "username": user.first_name,
                    }
                )
            
            return Response(
                    {
                        "Error": "User Not Found in Airtel Database"
                    },
                    status=status.HTTP_401_UNAUTHORIZED,
                )

        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            logging.info(
                f"There was an error processing your request.Exception line:{exc_tb.tb_lineno},Error:{e}"
            )
            return Response(
                    {
                        "Error": f"There was an error processing your request.Exception line:{exc_tb.tb_lineno},Error:{e}"
                    },
                    status=status.HTTP_401_UNAUTHORIZED,
                )


#### logout
@method_decorator(csrf_exempt, name='dispatch')
class LogoutView(generics.DestroyAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        try:
            request.user.auth_token.delete()
            # disConnectAllUserRouters(request.user.username)
            return Response(
                {"message": "Successfully logged out."}, status=status.HTTP_200_OK
            )
        except Exception as e:
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


#### check login status
class CheckLoginStatusView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        return Response({"message": "Authenticated"}, status=status.HTTP_200_OK)


####################################################################################################################################


class RMApprovalView(APIView):
    def get(self, request, id):
        new_id = signing.loads(id)
        request_instance = DCTSignupRequest.objects.get(id=new_id)
        if request_instance.current_status == "Pending Approval":
            send_approval_email_to_vertical_head(new_id)
            request_instance.current_status = (
                "Signup request Approved by RM. Sent to vertical head for approval."
            )
            request_instance.save()
            return Response(
                {
                    "message": "Signup request approved.Sent to vertical head for approval."
                },
                status=status.HTTP_200_OK,
            )
        else:
            return Response(
                {"message": "This link is expired. It is no longer valid."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


# create user and password to user
def create_mop_tool_user(id, password):
    print("Called create mop tool")
    request_instance = DCTSignupRequest.objects.get(id=id)
    username = request_instance.olmid
    email = request_instance.user_email
    # team = request_instance.team

    try:
        res_stat = requests.post(
            "http://10.227.244.108:10047/account/checkuser/",
            data={"username": username, "email": email, "password": password},
        )

        if res_stat.status_code == 201:
            return True
        return False
    except Exception as e:
        print(e)
        return False


class FinalApprovalView(APIView):
    def get(self, request, id):
        new_id = signing.loads(id)

        request_instance = DCTSignupRequest.objects.get(id=new_id)
        if request_instance.current_status == "Pending Approval":
            # password = generate_password()
            password = "You can use password of your olm id to login."
            print("Going for user creation")
            if create_mop_tool_user(new_id, password):
                send_credentials_email_to_user(new_id, password)
                request_instance.current_status = (
                    "Signup request approved.credentials sent to user."
                )
                request_instance.save()
                return Response(
                    {"message": "Signup request approved.credentials sent to user."},
                    status=status.HTTP_200_OK,
                )
            else:
                return Response(
                    {"message": "Unable to create user.Please contact team."},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )
        else:
            return Response(
                {"message": "This link is expired.It is no longer valid."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class RejectSignupRequestView(APIView):
    def get(self, request, id):
        new_id = signing.loads(id)
        request_instance = DCTSignupRequest.objects.get(id=new_id)
        if request_instance.current_status == "Pending Approval":
            request_instance.current_status = "Request rejected by reporting manager."
            request_instance.save()
            send_rejection_email_to_user(new_id, "Reporting Manager.")
            return Response(
                {"message": "Request rejected.Mail sent to user."},
                status=status.HTTP_200_OK,
            )
        elif (
            request_instance.current_status
            == "Signup request Approved by RM. Sent to vertical head for approval."
        ):
            request_instance.current_status = "Request rejected by Vertical head."
            request_instance.save()
            send_rejection_email_to_user(new_id, "Vertical Head.")
            return Response(
                {"message": "Request rejected.Mail sent to user."},
                status=status.HTTP_200_OK,
            )
        else:
            return Response(
                {"message": "This link is expired. It is no longer working."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class DTCSignupRequestView(APIView):
    def post(self, request, *args, **kwargs):
        # print(request.data)
        # serializer = MopSignupRequestSerializer(data=request.data)
        # if serializer.is_valid():
        #     serializer.save()

        # name =

        # user_email =

        # reporting_manager_email =

        olmid = request.data.get("username")
        print("################################", olmid)
        # user_type= request.data.get('user_type')
        vertical_head_email = request.data.get("HeadEmail")
        team = request.data.get("team")
        password = request.data.get("password")
        current_status = "Pending Approval"
        username1 = olmid
        vertical_head_email = "nazim.husain@airtel.com"
        try:
            if User.objects.filter(username=olmid).exists():
                return Response(
                    {
                        "success": False,
                        "message": "User with this email already exists.",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            ldap_server = "10.5.112.202"

            bind_dn = f"{username1}@india.airtel.itm"

            base_dn = "dc=india,dc=airtel,dc=itm"

            samaccountname = f"{olmid}"

            server = Server(ldap_server, get_info=ALL)

            conn = Connection(server, bind_dn, password, auto_bind=True)

            search_filter = f"(&(objectClass=user)(sAMAccountName={samaccountname}))"

            conn.search(
                search_base=base_dn,
                search_filter=search_filter,
                search_scope=SUBTREE,
                attributes=[
                    "sAMAccountName",
                    "manager1",
                    "supervisorMail",
                    "name",
                    "mail",
                    "memberOf",
                    "subFunction",
                    "subSubFunction",
                ],
            )

            results = conn.entries

            print("===============Result line number 339===============", results)

            entry_json = results[0].entry_to_json()

            entry_dict = json.loads(entry_json)

            user_email = entry_dict["attributes"]["mail"][0]
            reporting_manager_email = entry_dict["attributes"]["supervisorMail"][0]
            name = entry_dict["attributes"]["name"][0]

            user = User.objects.create_user(
                username=olmid, first_name=name, email=user_email, password=password
            )
            mis_request_instance = DCTSignupRequest(
                user_email=user_email,
                name=name,
                reporting_manager_email=reporting_manager_email,
                olmid=olmid,
                vertical_head_email=vertical_head_email,
                team=team,
                current_status=current_status,
            )
            mis_request_instance.save()
            token, _ = Token.objects.get_or_create(user=user)

            return Response(
                {
                    "success": True,
                    "token": str(token.key),
                    "message": "DRT signup successful.",
                },
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            print(e)
            exc_type, exc_obj, exc_tb = sys.exc_info()
            print(
                f"There was an error processing your request.Exception line:{exc_tb.tb_lineno},Error:{e}"
            )
            return Response(
                {"error": "There was some error."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
