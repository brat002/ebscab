# -*-coding: utf-8 -*-

from lib import digg_paginator
from lib import dictfetchall, instance_dict

from django.db import connection
import billservice.models as bsmodels
import datetime
from django.db import connection

from billservice.forms import TransactionReportForm, SearchAuthLogForm
from ebscab.lib.decorators import render_to, ajax_request

from django.core.urlresolvers import reverse
from tables import TemplateTable, TicketTable, AccountAddonServiceTable, IPInUseTable,  LogTable, BallanceHistoryTable, \
                          SubAccountsTable, AccountHardwareTable, SuspendedPeriodTable, AccountTarifTable, TotalTransactionReportTable, \
                          AccountsReportTable, AuthLogTable, ActiveSessionTable, NasTable, TransactionReportTable, AddonServiceTransactionReportTable, PeriodicalServiceTransactionReportTable, \
                          TrafficTransactionReportTable, AccountSuppAgreementTable
from django.http import HttpResponseRedirect
from django_tables2_reports.config import RequestConfigReport as RequestConfig
from django_tables2_reports.utils import create_report_http_response
from django_tables2 import RequestConfig as DTRequestConfig
from billservice.forms import SearchAccountForm, AccountExtraForm

from ebsadmin.transactionreport import TRANSACTION_MODELS, model_by_table

from billservice.models import Account, Transaction, TransactionType, PeriodicalServiceHistory, PeriodicalService, AccountAddonService, TotalTransactionReport as TransactionReport, OneTimeServiceHistory, SubAccount, AccountTarif, SuspendedPeriod, AccountHardware,\
    AddonServiceTransaction, SwitchPort
from billservice.forms import SubAccountForm, SubAccountPartialForm, AccountAddonService, TransactionModelForm
from billservice.models import SubAccount, AddonService, BalanceHistory, IPInUse
from billservice.forms import TransactionReportForm, TransactionModelForm, AddonServiceForm, BallanceHistoryForm, TemplateSelectForm
from billservice.forms import AccountSuppAgreementForm, AccountAddonServiceModelForm, AccountHardwareForm
from billservice.models import AccountSuppAgreement, TotalTransactionReport, AccountHardware, SuspendedPeriod, Organization, BankData, TrafficTransaction, Template, AccountPrepaysRadiusTrafic, AccountPrepaysTime, AccountPrepaysTrafic
from billservice.forms import AccountTariffForm, AccountForm, SuspendedPeriodModelForm, OrganizationForm, BankDataForm, IpInUseLogForm, TemplateForm
from helpdesk.models import Ticket
from radius.forms import SessionFilterForm
from radius.models import AuthLog, ActiveSession
from object_log.models import LogItem
import simplejson as json
from django.db.models import Q
import IPy, ipaddr
from object_log.models import LogItem
from django.contrib.contenttypes.models import ContentType
from nas.models import Nas
from nas.forms import NasForm

from django.db.models import Sum
from django.contrib import messages
from django.contrib.auth.models import User
log = LogItem.objects.log_action
from billservice.helpers import systemuser_required
BAD_REQUEST = u"Ошибка передачи параметров"

from django.utils.translation import ugettext_lazy as _
from ebsadmin.management import subaccount_ipn_recreate, subaccount_ipn_delete 

def compare(old, new):
    r = {}
    for key in new:
        if new[key]!=old.get(key):
            r[key]=new[key]
    return r
        
def gettransactiontypes(current=[]):
        res = []
        for t in TransactionType.objects.all():
            d=[]
            if t.internal_name=='PS_AT_START':
                pstypes = PeriodicalService.objects.filter(cash_method='AT_START')
                d=[]
                for pstype in pstypes:
                    key = 'PS_AT_START___%s' % pstype.id
                    d.append({'title':pstype.name, 'key': key, 'select': True if key in current else False})
            if t.internal_name=='PS_AT_END':
                pstypes = PeriodicalService.objects.filter(cash_method='AT_END')
                d=[]
                for pstype in pstypes:
                    key = 'PS_AT_END___%s' % pstype.id
                    d.append({'title':pstype.name, 'key': key, 'select': True if key in current else False})
                    
            if t.internal_name=='PS_GRADUAL':
                pstypes = PeriodicalService.objects.filter(cash_method='GRADUAL')
                d=[]
                for pstype in pstypes:
                    key = 'PS_GRADUAL___%s' % pstype.id
                    d.append({'title':pstype.name, 'key': key, 'select': True if key in current else False})
            #---
            if t.internal_name=='ADDONSERVICE_PERIODICAL_GRADUAL':
                pstypes = AddonService.objects.filter(sp_type='GRADUAL')
                d=[]
                for pstype in pstypes:
                    key =  'ADDONSERVICE_PERIODICAL_GRADUAL___%s' % pstype.id
                    d.append({'title':pstype.name, 'key': key, 'select': True if key in current else False})
                    
            if t.internal_name=='ADDONSERVICE_PERIODICAL_AT_START':
                pstypes = AddonService.objects.filter(sp_type='AT_START')
                d=[]
                for pstype in pstypes:
                    key =  'ADDONSERVICE_PERIODICAL_AT_START___%s' % pstype.id
                    d.append({'title':pstype.name, 'key': key, 'select': True if key in current else False})
            if t.internal_name=='ADDONSERVICE_PERIODICAL_AT_END':
                pstypes = AddonService.objects.filter(sp_type='AT_END')
                d=[]
                for pstype in pstypes:
                    key = 'ADDONSERVICE_PERIODICAL_AT_END___%s' % pstype.id
                    d.append({'title':pstype.name, 'key': key, 'select': True if key in current else False})
            if t.internal_name=='ADDONSERVICE_ONETIME':
                pstypes = AddonService.objects.filter(service_type='onetime')
                d=[]
                for pstype in pstypes:
                    key =  'ADDONSERVICE_ONETIME___%s' % pstype.id
                    d.append({'title':pstype.name, 'key': key, 'select': True if key in current else False})
            #---
            res.append({'title': t.name, 'key': t.internal_name, 'children':d, 'isFolder':True if d else False, 'select': True if t.internal_name in current else False})
            
        res = json.dumps({'title': u'Все', 'key':'all', 'children': res, 'isFolder':True, 'select': True}, ensure_ascii=False)
        return res
            
@systemuser_required
@render_to('ebsadmin/transactionreport_list.html')
def transactionreport2(request):
    if  not (request.user.account.has_perm('billservice.view_transaction')):
        messages.error(request, _(u'У вас нет прав на доступ в этот раздел.'), extra_tags='alert-danger')
        return HttpResponseRedirect('/ebsadmin/')
    
    if request.GET:
        data = request.GET
        #pageitems = 100
        
        form = TransactionReportForm(request.GET)
        only_payments = request.GET.get("only_payments")
        only_credits = request.GET.get("only_credits")
        if form.is_valid():
            
            #items = PeriodicalServiceHistory.objects.all()[0:200]
            page = int(request.GET.get("page", 1))
           
            if "all" in request.GET:
                per_page=10000000000000000
            else:
                 per_page = int(request.GET.get("per_page", 25))

                    
            pageitems = per_page
            sort = request.GET.get("sortpaginate=True if not request.GET.get('paginate')=='False' else False", '-created')
            account = form.cleaned_data.get('account')
            start_date = form.cleaned_data.get('start_date')
            end_date = form.cleaned_data.get('end_date')
            

            systemusers = form.cleaned_data.get('systemuser')
            promise = form.cleaned_data.get('promise')
            

            cur = connection.cursor()
            trtypes = data.getlist('tree')

                        
              
            with_id = []
            by_groups = {}
            tr_types = []
            for tr in trtypes:
                l = tr.split("___")
                tr_type = l[0]
                tr_types.append(tr_type)
                id = None

                if len(l)==2:
                    tr_type, id = l
                parent_tr_type = TRANSACTION_MODELS.get(tr_type, 'Transaction')

                if parent_tr_type not in by_groups:
                    by_groups[parent_tr_type] = []
                if id:
                    by_groups[parent_tr_type].append(id)
                elif parent_tr_type=='Transaction':
                    by_groups[parent_tr_type].append(tr_type)
                    

            res = []
            total_summ = 0
            for key in by_groups:
                continue
                if key=='PeriodicalServiceHistory':
                    items = PeriodicalServiceHistory.objects.filter(service__id__in=by_groups[key])
                    if only_credits:
                        items = items.filter(summ__lte=0)
                    if account:
                        items = items.filter(account__id__in=account)
                    if start_date:
                        items = items.filter(created__gte=start_date)
                    if end_date:

                        items = items.filter(created__lte=end_date)
                    total_summ += float(items.aggregate(Sum("summ"))['summ__sum'] or 0)
                    res += items.values('id',  'account',  'account__username', 'account__city__name', 'account__street', 'account__house', 'account__room', 'account__fullname', 'summ', 'created', 'type__name', 'service__name')

                if key=='AddonServiceTransaction':
                    items = AddonServiceTransaction.objects.filter(service__id__in=by_groups[key])
                    if only_credits:
                        items = items.filter(summ__lte=0)
                    if account:
                        items = items.filter(account__id__in=account)
                    if start_date:
                        items = items.filter(created__gte=start_date)
                    if end_date:

                        items = items.filter(created__lte=end_date)
                    total_summ += float(items.aggregate(Sum("summ"))['summ__sum'] or 0)
                    res += items.values('id',  'account', 'account__username', 'account__city__name', 'account__street', 'account__house', 'account__room', 'account__fullname', 'summ', 'created', 'type__name', 'service__name')

                if key=='TrafficTransaction':
                    items = TrafficTransaction.objects.all()
                    if only_credits:
                        items = items.filter(summ__lte=0)
                    if account:
                        items = items.filter(account__id__in=account)
                    if start_date:
                        items = items.filter(created__gte=start_date)
                    if end_date:

                        items = items.filter(created__lte=end_date)
                    total_summ += float(items.aggregate(Sum("summ"))['summ__sum'] or 0)
                    res += items.values('id',  'account', 'account__username', 'account__city__name', 'account__street', 'account__house', 'account__room', 'account__fullname', 'summ', 'created')
                    
                if key=='Transaction':

                    items = Transaction.objects.filter(type__internal_name__in=by_groups[key])
                    if only_credits:
                        items = items.filter(summ__lte=0)
                    if only_payments:
                        items = items.filter(summ__gte=0)
                    if account:

                        items = items.filter(account__id__in=account)
                    if start_date:

                        items = items.filter(created__gte=start_date)
                    if end_date:

                        items = items.filter(created__lte=end_date)
                    if systemusers:
                        items = items.filter(systemuser__in=systemusers)
                    total_summ += float(items.aggregate(Sum("summ"))['summ__sum'] or 0)
                    res += items.values('id', 'account', 'account__username', 'account__city__name', 'account__street', 'account__house', 'account__room', 'account_fullname', 'summ', 'created', 'type__name', 'bill', 'description')
           
                    
            summOnThePage = 1500
            summ = total_summ
            total = False
            tf = TransactionReportForm(request.GET)
            print by_groups, len(by_groups)
            if len(by_groups)==1 and 'TrafficTransaction' in by_groups:
                res = TrafficTransaction.objects.all()
                table = TrafficTransactionReportTable
            elif len(by_groups)==1 and by_groups.get('Transaction'):
                res = Transaction.objects.all()
                table = TransactionReportTable
            elif len(by_groups)==1 and 'AddonServiceTransaction' in by_groups:
                res = AddonServiceTransaction.objects.all()
                table = AddonServiceTransactionReportTable
            elif len(by_groups)==1 and 'PeriodicalServiceHistory' in by_groups:
                res = PeriodicalServiceHistory.objects.all()
                table = PeriodicalServiceTransactionReportTable    
            else:
                res = TotalTransactionReport.objects.all()
                table = TotalTransactionReportTable    
                total=True
            
            if account:
                res = res.filter(account__in=account)
            if start_date:
                res = res.filter(created__gte=start_date)
            if end_date:
                res = res.filter(created__lte=end_date )
            if tr_types and table not in (TrafficTransactionReportTable, PeriodicalServiceTransactionReportTable):
                res = res.filter(type__internal_name__in=tr_types)
                
            if table in (AddonServiceTransactionReportTable, ):
                res = res.filter(service__id__in=by_groups.get('AddonServiceTransaction', []))
                
            if table in (PeriodicalServiceTransactionReportTable, ):                
                res = res.filter(service__id__in=by_groups.get('PeriodicalServiceHistory', []))
                
            if table == TransactionReportTable and systemusers:
                res = res.filter(systemuser__in=systemusers)
            
            if only_credits:
                res = res.filter(summ__lte=0)
            if only_payments:
                res = res.filter(summ__gte=0)
                        
            total_summ = "%.2f" % (res.aggregate(total_summ=Sum('summ')).get('total_summ') or 0)
            if table==TotalTransactionReportTable:
                table = table(res.prefetch_related('tariff__name',  'type__name').values('id', 'account__username', 'account__city__name', 'account__street', 'account__house', 'account__room', 'account__fullname', 'account', 'summ', 'created', 'tariff__name', 'bill', 'description', 'end_promise', 'promise_expired', 'type__name', 'service_id', 'table', 'prev_balance', 'is_bonus'))
            elif table == TrafficTransactionReportTable:
                table = table(res.prefetch_related('account__username').values('id', 'account__username', 'account__city__name', 'account__street', 'account__house', 'account__room', 'account__fullname', 'account', 'summ', 'created', ))
                
            elif table ==TransactionReportTable:
                table = table(res.prefetch_related('type__name', 'account__username', 'systemuser__username').values('id', 'account__username', 'account__city__name', 'account__street', 'account__house', 'account__room', 'account__fullname', 'account', 'summ', 'description', 'bill', 'created',  'type__name', 'end_promise', 'promise_expired', 'systemuser__username', 'prev_balance', 'is_bonus'))
            elif table in (PeriodicalServiceTransactionReportTable,):
                table = table(res.prefetch_related('type__name', 'account__username', 'service__name').values('id', 'account__username', 'account', 'account__city__name', 'account__street', 'account__house', 'account__room', 'account__fullname', 'summ', 'created', 'service__name', 'type__name', 'prev_balance', 'real_created'))
            elif table in (AddonServiceTransactionReportTable,):
                table = table(res.prefetch_related('type__name', 'account__username', 'service__name').values('id', 'account__username', 'account', 'account__city__name', 'account__street', 'account__house', 'account__room', 'account__fullname', 'summ', 'created', 'service__name', 'type__name', 'prev_balance'))

            else:
                table = table(res)
                

            table_to_report = RequestConfig(request, paginate=False if request.GET.get('paginate')=='False' else True).configure(table)
            if table_to_report:
                return create_report_http_response(table_to_report, request)

            r = gettransactiontypes(current=trtypes)
            return {"table": table,  'form':tf, 'ojax':r, 'total_summ': total_summ, 'total': total}

        else:
            res = gettransactiontypes(current=data.getlist('tree'))
            return {'status':False, 'form':form, 'ojax':res}
    else:
        res = gettransactiontypes(current=request.GET.getlist('tree'))
        form = TransactionReportForm(request.GET, initial={'start_date': datetime.datetime.now()-datetime.timedelta(days=36500)})
        return { 'form':form, 'ojax': res}   
    
        
@systemuser_required
@render_to('ebsadmin/accounts_list.html')
def accountsreport(request):
        
    if  not (request.user.account.has_perm('billservice.view_account')):
        messages.error(request, _(u'У вас нет прав на доступ в этот раздел.'), extra_tags='alert-danger')
        return HttpResponseRedirect('/ebsadmin/')

    if request.method=='GET':
        data = request.GET or request.POST

        if not data:
            form = SearchAccountForm()
            return { 'form':form}   
        
        form = SearchAccountForm(data)
        if form.is_valid():
            
            date_start, date_end = None, None
            account = form.cleaned_data.get('account')+form.cleaned_data.get('fullname')+form.cleaned_data.get('contactperson')+form.cleaned_data.get('username')+form.cleaned_data.get('contract') # - concatenate tuples
            account_text = request.GET.get('account_text')
            username_text = request.GET.get('username_text')
            contract_text = request.GET.get('contract_text')
            fullname_text = request.GET.get('fullname_text')
            contactperson_text = request.GET.get('contactperson_text')
            id = form.cleaned_data.get('id')
            passport = form.cleaned_data.get('passport')
            created = form.cleaned_data.get('created')
            tariff = form.cleaned_data.get('tariff')
            street = form.cleaned_data.get('street')
            room = form.cleaned_data.get('room')
            city = form.cleaned_data.get('city')
            row = form.cleaned_data.get('row')
            house = form.cleaned_data.get('house')
            house_bulk = form.cleaned_data.get('house_bulk')
            ballance = form.cleaned_data.get('ballance')
            #ballance_exp = form.cleaned_data.get('ballance_exp')
            vpn_ip_address = form.cleaned_data.get('vpn_ip_address')
            ipn_ip_address = form.cleaned_data.get('ipn_ip_address')
            ipn_mac_address = form.cleaned_data.get('ipn_mac_address')
            elevator_direction = form.cleaned_data.get('elevator_direction')
            nas = form.cleaned_data.get('nas')
            deleted = form.cleaned_data.get('deleted')
            ipn_status = form.cleaned_data.get('ipn_status')
            organization = form.cleaned_data.get('organization')
            phone = form.cleaned_data.get('phone')
            suppagreement = form.cleaned_data.get('suppagreement')
            addonservice = form.cleaned_data.get('addonservice')

            credit = form.cleaned_data.get('credit')
            #credit_exp = form.cleaned_data.get('credit_exp')
                        
            status = int(form.cleaned_data.get('status', 0)or 0)
            
            if type(created)==tuple:
                date_start, date_end = created
            systemuser = form.cleaned_data.get('systemuser')

            if deleted:
                res = Account.objects.deleted_set()
            else:
                res = Account.objects.all()
                
            if id:
                res = res.filter(id=id)
            if room:
                res = res.filter(room__icontains=room)

                
            if account:
                res = res.filter(id__in=account)
                
            if account_text:
                res = res.filter(username__icontains=account_text)
                
            if username_text:
                res = res.filter(username__icontains=username_text)
                
            if contract_text:
                res = res.filter(contract__icontains=contract_text)

            if fullname_text:
                res = res.filter(fullname__icontains=fullname_text)
                
            if contactperson_text:
                res = res.filter(contactperson__icontains=contactperson_text)
            if systemuser:
                res = res.filter(systemuser=systemuser)
            
            if suppagreement:
                res = res.filter(accountsuppagreement__suppagreement=suppagreement)
                
            if addonservice:
                res = res.filter(accountaddonservice__service=addonservice)
            if date_start:
                res = res.filter(created__gte=date_start)
            if date_end:
                res = res.filter(created__lte=date_end)
                
            if not (date_start and date_end) and created:
                res = res.filter(created=created)
            if tariff:
                res = res.extra(where=['billservice_account.id in (SELECT account_id FROM billservice_accounttarif WHERE id in (SELECT max(id) FROM billservice_accounttarif GROUP BY account_id HAVING account_id IN (SELECT id FROM billservice_account) AND MAX(datetime) <= now()) and tarif_id in %s)'], params=[ tuple(['%s' % x.id for x in tariff]) ])
            
            if city:
                res = res.filter(city=city)
            if street:
                res = res.filter(street__icontains=street)

            if house:
                res = res.filter(house__icontains=house)

            if row:
                res = res.filter(row=row)
                
            if elevator_direction:
                res = res.filter(elevator_direction=elevator_direction)
            
            if phone:
                res = res.filter(Q(phone_h__contains=phone)| Q(phone_m__contains=phone))
                
            if status:
                res = res.filter(status=status)

            if passport:
                res = res.filter(passport__icontains=passport)
                
            if vpn_ip_address:
                res = res.filter(subaccounts__vpn_ip_address=vpn_ip_address)

            if ipn_ip_address:
                res = res.filter(subaccounts__ipn_ip_address=ipn_ip_address)

            if ipn_mac_address:
                res = res.filter(subaccounts__ipn_mac_address__icontains=ipn_mac_address)

            if nas:
                res = res.filter(subaccounts__nas__in=nas)
            
            if organization:
                res = res.filter(Q(organization__in=organization))

            if ipn_status and 'undefined' not in ipn_status:
                res = res.filter(subaccounts__ipn_added='added' in ipn_status, subaccounts__ipn_enabled='enabled')
                
            if type(ballance)==tuple:
                cond, value = ballance
                if cond==">":
                    res = res.filter(ballance__gte=value)
                elif cond=="<":
                    res = res.filter(ballance__lte=value)
            elif ballance:
                res = res.filter(ballance=ballance)
                    
            if type(credit)==tuple:
                cond, value = credit
                if cond==">":
                    res = res.filter(credit__gte=value)
                elif cond=="<":
                    res = res.filter(credit__lte=value)
            elif credit:
                res = res.filter(credit=credit)
                    
            res = res.distinct()
            
            table = AccountsReportTable(res)
            table_to_report = RequestConfig(request, paginate=False if request.GET.get('paginate')=='False' else True).configure(table)
            if table_to_report:
                return create_report_http_response(table_to_report, request)

            #===================================================================
            #for kq in connection.queries:
            #    print kq
            return {"table": table,  'form':form, 'resultTab':True}   
    
        else:
            print form._errors
            return {'status':False, 'form':form}
    else:
        form = SearchAccountForm()
        return { 'form':form}   
    
@systemuser_required
@render_to('ebsadmin/authlog_list.html')
def authlogreport(request):
        
    if  not (request.user.account.has_perm('radius.view_authlog')):
        messages.error(request, _(u'У вас нет прав на доступ в этот раздел.'), extra_tags='alert-danger')
        return HttpResponseRedirect('/ebsadmin/')

    if request.method=='GET' and request.GET:
        data = request.GET

        #pageitems = 100
        form = SearchAuthLogForm(data)
        if form.is_valid():
            
            account = form.cleaned_data.get('account')
            nas = form.cleaned_data.get('nas')
            start_date, end_date = request.GET.get('start_date'),  request.GET.get('end_date')
            
            
            
            res = AuthLog.objects.all()
            if account:
                res = res.filter(account__in=account)
            
            if nas:
                res = res.filter(nas__in=nas)

            
            if start_date:
                res = res.filter(datetime__gte=start_date)
            if end_date:
                res = res.filter(datetime__lte=end_date)
            
            table = AuthLogTable(res)
            table_to_report = RequestConfig(request,paginate=False if request.GET.get('paginate')=='False' else True).configure(table)
            if table_to_report:
                return create_report_http_response(table_to_report, request)
            
            
            return {"table": table,  'form':form, 'resultTab':True}   
    
        else:
            return {'status':False, 'form':form}
    else:
        form = SearchAuthLogForm()
        return { 'form':form}   
    
@systemuser_required
@render_to('ebsadmin/ipinuse_list.html')
def ipinusereport(request):
        
    if  not (request.user.account.has_perm('billservice.view_ipinuse')):
        messages.error(request, _(u'У вас нет прав на доступ в этот раздел.'), extra_tags='alert-danger')
        return HttpResponseRedirect('/ebsadmin/')

    if request.method=='GET' and request.GET:
        data = request.GET

        #pageitems = 100
        form = IpInUseLogForm(data)
        if form.is_valid():
            
            account = form.cleaned_data.get('account')
            subaccount = form.cleaned_data.get('subaccount')
            types = form.cleaned_data.get('types')
            ip = form.cleaned_data.get('ip')
            ippool = form.cleaned_data.get('ippool')

            start_date = form.cleaned_data.get('start_date')
            end_date = form.cleaned_data.get('end_date')

            res = IPInUse.objects.select_related().all()
            if account:
                #print account
                subaccs = SubAccount.objects.filter(account__id__in=account)
                t = [x.vpn_ipinuse_id for x in subaccs]+ [x.ipn_ipinuse_id for x in subaccs]
                #print t
                for subacc in subaccs:
                    res = res.filter(Q(activesession__ipinuse__isnull=False) | Q(activesession__subaccount=subacc))
                res = res.filter(id__in=t)
                

            if ip:
                res = res.filter(ip=ip)
            if types:
                if 'static' in types:
                    res = res.filter(dynamic=False)
                elif 'dynamic' in types:
                    res = res.filter(dynamic=True)


            if start_date:
                res = res.filter(datetime__gte=start_date)
            if end_date:
                res = res.filter(datetime__lte=end_date)
            
            if ippool:
                res = res.filter(pool__in=ippool)
                
            table = IPInUseTable(res)
            table_to_report = RequestConfig(request, paginate=False if request.GET.get('paginate')=='False' else True).configure(table)
            if table_to_report:
                return create_report_http_response(table_to_report, request)

            return {"table": table,  'form':form, 'resultTab':True}   
    
        else:
            return {'status':False, 'form':form}
    else:
        form = IpInUseLogForm()
        return { 'form':form}   
    
@systemuser_required
@render_to('ebsadmin/ballancehistory_list.html')
def ballancehistoryreport(request):
        
    if  not (request.user.account.has_perm('billservice.view_balancehistory')):
        messages.error(request, _(u'У вас нет прав на доступ в этот раздел.'), extra_tags='alert-danger')
        return HttpResponseRedirect('/ebsadmin/')
    

    if request.method=='GET' and request.GET:
        form = BallanceHistoryForm(request.GET)
        if form.is_valid():
            
            account = form.cleaned_data.get('account')
            start_date = form.cleaned_data.get('start_date')
            end_date = form.cleaned_data.get('end_date')

            res = BalanceHistory.objects.all()
            if account:
                res = res.filter(account__in=account)
            

            
            if start_date:
                res = res.filter(datetime__gte=start_date)
            if end_date:
                res = res.filter(datetime__lte=end_date)
            res = res.values('id', 'account', 'account__username', 'balance', 'summ',  'datetime')
            table = BallanceHistoryTable(res)
            table_to_report = RequestConfig(request, paginate=False if request.GET.get('paginate')=='False' else True).configure(table)
            if table_to_report:
                return create_report_http_response(table_to_report, request)
            
            
            return {"table": table,  'form':form, 'resultTab':True}   
    
        else:
            return {'status':False, 'form':form}
    else:
        form = BallanceHistoryForm()
        return { 'form':form}  
    
@systemuser_required
@render_to('ebsadmin/account_edit.html')
def accountedit(request):
    
    subaccounts_table = None
    accounttarif_table = None
    accounthardware_table = None
    suspendedperiod_table = None
    accountaddonservice_table = None
    accountsuppagreement_table = None
    accountsupp = None
    account_id = request.GET.get("id")

    account = None
    org_form = None
    bank_form = None
    action_log_table = None
    org = None
    prepaidradiustraffic = 0
    prepaidradiustime = 0
    ticket_table = None
    prepaidtraffic = []
    extra_form = None
    if account_id:
        if  not (request.user.account.has_perm('billservice.change_account')):
            messages.error(request, _(u'У вас нет прав на редактирование аккаунтов'), extra_tags='alert-danger')
            return HttpResponseRedirect(request.path)

        account = Account.objects.all_with_deleted().get(id=account_id)
        

            

        res = SubAccount.objects.filter(account=account)
        subaccounts_table = SubAccountsTable(res)
        DTRequestConfig(request, paginate = False).configure(subaccounts_table)
    
        res = AccountTarif.objects.filter(account=account)
        accounttarif_table = AccountTarifTable(res)
        DTRequestConfig(request, paginate = False).configure(accounttarif_table)
    
        res = AccountHardware.objects.filter(account=account)
        accounthardware_table = AccountHardwareTable(res)
        DTRequestConfig(request, paginate = False).configure(accounthardware_table)
    
        res = SuspendedPeriod.objects.filter(account=account)
        suspendedperiod_table = SuspendedPeriodTable(res)
        DTRequestConfig(request, paginate = False).configure(suspendedperiod_table)
    
        res = AccountAddonService.objects.filter(account=account)
        accountaddonservice_table = AccountAddonServiceTable(res)
        DTRequestConfig(request, paginate = False).configure(accountaddonservice_table)
        
        res = AccountSuppAgreement.objects.filter(account=account)
        accountsupp = AccountSuppAgreement.objects.filter(account=account, closed__isnull=True)

        accountsuppagreement_table = AccountSuppAgreementTable(res)
        DTRequestConfig(request, paginate = False).configure(AccountSuppAgreementTable(res))
        try:
            res = Ticket.objects.filter(Q(owner=User.objects.get(username=account.username)) | Q(account=account)) 
            ticket_table = TicketTable(res)
            DTRequestConfig(request, paginate = False).configure(ticket_table)
        except:
            pass

    else:
        if  not (request.user.account.has_perm('billservice.add_account')):
            messages.error(request, _(u'У вас нет прав на создание аккаунтов'), extra_tags='alert-danger')
            return HttpResponseRedirect(request.path)
    
    subaccount_form = None
    subaccounts_count = 0
    if account and request.method=='POST':
    
        subaccounts_count = SubAccount.objects.filter(account=account).count()
    
    
        if subaccounts_count==1:
            subaccount = SubAccount.objects.filter(account=account)[0]
            subaccount_form = SubAccountPartialForm(request.POST, instance=subaccount, prefix='subacc')
    elif account and request.method=='GET':
  
        subaccounts_count = SubAccount.objects.filter(account=account).count()
    
    
        if subaccounts_count==1:
            subaccount = SubAccount.objects.filter(account=account)[0]
            subaccount_form = SubAccountPartialForm( instance=subaccount, prefix='subacc')        
    else:

        subaccount_form = SubAccountPartialForm(request.POST, prefix='subacc')
    

    if request.method=='POST':
     
        if account and request.POST:
            form = AccountForm(request.POST, instance=account)
            org = Organization.objects.filter(account=account)



                
            if org:
                org_form = OrganizationForm(request.POST, instance=org[0], prefix='org')
                bank = org[0].bank
                if bank:
                    bank_form = BankDataForm(request.POST, instance=bank, prefix='bankdata')
                else:
                    bank_form = BankDataForm(request.POST, prefix='bankdata')

            else:
                #print request.POST
                org_form = OrganizationForm(request.POST, prefix='org')
                
                bank_form = BankDataForm(request.POST, prefix='bankdata')
                

        else:
            form = AccountForm(request.POST)
            org_form = OrganizationForm(request.POST, prefix='org')
            bank_form = BankDataForm(request.POST, prefix='bankdata')
        
        
     
        extra_form = AccountExtraForm(request.POST, instance=account)
        
        

          
        if form.is_valid():
        
            if not org_form.is_valid():

                return {'subaccount_form': subaccount_form, 
                        'extra_form': extra_form, 
                        'org_form':org_form, 
                        'prepaidtraffic':prepaidtraffic,  
                        'prepaidradiustraffic':prepaidradiustraffic, 
                        'prepaidradiustime':prepaidradiustime, 
                        'bank_form': bank_form, 
                        "accounttarif_table": accounttarif_table, 
                        'accountaddonservice_table':accountaddonservice_table, 
                        "account":account, 
                        'subaccounts_table':subaccounts_table, 
                        'accounthardware_table': accounthardware_table, 
                        'suspendedperiod_table': suspendedperiod_table,  
                        'accountsuppagreement_table': accountsuppagreement_table,
                        'accountsupp': accountsupp,
                        'form':form}
            
      
            model =form.save(commit=False)
            model.save()
            contract_num = form.cleaned_data.get("contract_num")

            if subaccounts_count<=1:

                new = False
                if subaccounts_count==0:
                    subaccount = SubAccount(account=model)
                    subaccount.save()
                    new = True
                    subaccount_form = SubAccountPartialForm(request.POST, instance = subaccount, prefix='subacc')
                else:
                    subaccount = SubAccount.objects.filter(account=model)[0]

                subaccount_form = SubAccountPartialForm(request.POST, instance=subaccount, prefix='subacc')
                    
                if subaccount_form.is_valid():

                    
                    subacc_model = subaccount_form.save(commit=False)
                    if subacc_model.username or subacc_model.nas or subacc_model.ipn_ip_address or subacc_model.vpn_ip_address or subacc_model.vpn_ipv6_ip_address or subacc_model.ipv4_vpn_pool or subacc_model.ipv4_ipn_pool or subacc_model.switch:
                        subacc_model.save()
                        log('EDIT', request.user, subacc_model) if id else log('CREATE', request.user, subacc_model)
                    else:
                         subacc_model.delete()
                else:
                    if new == True:
                        subaccount.delete()

                    if subaccount_form.errors:
                        for k, v in subaccount_form._errors.items():
                            messages.error(request, '%s=>%s' % (k, ','.join(v)), extra_tags='alert-danger')
                    return {'subaccount_form': subaccount_form, 
                            'extra_form': extra_form, 
                            'org_form':org_form, 
                            'prepaidtraffic':prepaidtraffic,  
                            'prepaidradiustraffic':prepaidradiustraffic, 
                            'prepaidradiustime':prepaidradiustime, 
                            'bank_form': bank_form, 
                            "accounttarif_table": accounttarif_table, 
                            'accountaddonservice_table':accountaddonservice_table, 
                            "account":account, 
                            'subaccounts_table':subaccounts_table, 
                            'accounthardware_table': accounthardware_table, 
                            'suspendedperiod_table': suspendedperiod_table,  
                            'accountsuppagreement_table': accountsuppagreement_table,
                            'accountsupp': accountsupp,
                            'form':form}


            if not model.contract and contract_num:
                contract_template = contract_num.template
                contract_counter = contract_num.counter or 1
    
                year=model.created.year
                month=model.created.month
                day=model.created.day
                hour=model.created.hour
                minute=model.created.minute
                second=model.created.second

                accid = model.id
                username = model.username
            
                d={'account_id':accid,'username':username, 'year':year,'month':month, 'day':day, 'hour':hour, 'minute':minute,'second':second, 'contract_num':contract_counter}
            #d.update(model.__dict__)

                
                contract = (contract_template % d) if contract_template else '' 
                model.contract = contract
                model.save()

                contract_num.count = contract_counter
                contract_num.save()
                    

                            
            #print dir(org_form) 
            if form.cleaned_data.get('organization'):
                org_model = org_form.save(commit=False)
                if request.POST.get("bankdata-bank"):
    
                    bank_model = bank_form.save(commit=False)
                    bank_model.save()
                    org_model.bank=bank_model
    
                org_model.acount=model
                org_model.save()
            elif org: # if not organization and organization for account exists
                org.delete()
                

            log('EDIT', request.user, model) if id else log('CREATE', request.user, model) 
            messages.success(request, u'Аккаунт сохранён.', extra_tags='alert-success')
            return HttpResponseRedirect("%s?id=%s" % (reverse("account_edit"), model.id))
        else:

            if form._errors:
                for k, v in form._errors.items():
                    messages.error(request, '%s=>%s' % (k, ','.join(v)), extra_tags='alert-danger')

            if extra_form._errors:
                for k, v in extra_form._errors.items():
                    messages.error(request, '%s=>%s' % (k, ','.join(v)), extra_tags='alert-danger')
            if org_form._errors:
                for k, v in org_form._errors.items():
                    messages.error(request, '%s=>%s' % (k, ','.join(v)), extra_tags='alert-danger')
            if bank_form._errors:
                for k, v in bank_form._errors.items():
                    messages.error(request, '%s=>%s' % (k, ','.join(v)), extra_tags='alert-danger')
                
            return {'subaccount_form': subaccount_form,
                    'extra_form': extra_form, 
                    'ticket_table': ticket_table, 
                    'org_form':org_form, 
                    'bank_form': bank_form,  
                    'prepaidtraffic':prepaidtraffic, 
                    'prepaidradiustraffic':prepaidradiustraffic,
                    'prepaidradiustime':prepaidradiustime,  
                    "accounttarif_table": accounttarif_table, 
                    'accountaddonservice_table':accountaddonservice_table, 
                    "account":account, 
                    'subaccounts_table':subaccounts_table, 
                    'accounthardware_table': accounthardware_table, 
                    'suspendedperiod_table': suspendedperiod_table,  
                    'accountsuppagreement_table': accountsuppagreement_table,
                    'accountsupp': accountsupp, 
                    'form':form}
    if account:
        
        
        org = Organization.objects.filter(account=account)
        if org:
            org_form = OrganizationForm(instance=org[0], prefix='org')
            bank = None
            if org[0].bank:
                bank = org[0].bank
                bank_form = BankDataForm(instance=bank, prefix='bankdata')
                
            form = AccountForm(initial={'organization':True}, instance=account)
                
        else:
            org_form = OrganizationForm(initial={'account': account}, prefix='org')
            bank_form = BankDataForm(prefix='org')
            form = AccountForm(instance=account)
            extra_form = AccountExtraForm(instance=account)
    else:
        form = AccountForm(initial={'credit': 0, 'ballance':0, 'created': datetime.datetime.now()})
        extra_form = AccountExtraForm()
        org_form = OrganizationForm(prefix='org')
        bank_form = BankDataForm(prefix='org')
    if not subaccount_form and subaccounts_count==0:
        subaccount_form = SubAccountPartialForm(request.POST, prefix='subacc')
    return { 'form':form, 'subaccount_form': subaccount_form, 'extra_form': extra_form, 'org_form':org_form, 'bank_form': bank_form,  "accounttarif_table": accounttarif_table, 'accountaddonservice_table':accountaddonservice_table, "account":account, 'subaccounts_table':subaccounts_table, 'accounthardware_table': accounthardware_table, 'suspendedperiod_table': suspendedperiod_table, 
            'accountsuppagreement_table': accountsuppagreement_table, 'ticket_table': ticket_table, 'accountsupp': accountsupp} 

@systemuser_required
@render_to('ebsadmin/subaccount_edit.html')
def subaccountedit(request):
    
    id = request.GET.get("id")
    account_id = request.GET.get("account_id")
    ipn_ipinuse = None
    vpn_ipinuse = None
    
    subaccount = None
    table =None
    action_log_table = None
    if id:
        if  not (request.user.account.has_perm('billservice.change_subaccount')):
            messages.error(request, _(u'У вас нет прав на редактирование субаккаунтов'), extra_tags='alert-danger')
            return HttpResponseRedirect(request.path)
        subaccount = SubAccount.objects.get(id=id)
    
        res = AccountAddonService.objects.filter(subaccount=subaccount)
        table = AccountAddonServiceTable(res)
        table_to_report = DTRequestConfig(request, paginate=False).configure(table)
        if table_to_report:
            return create_report_http_response(table_to_report, request)
        


        res = []
        prev = None
    else:
        if  not (request.user.account.has_perm('billservice.add_subaccount')):
            messages.error(request, _(u'У вас нет прав на создание аккаунтов'), extra_tags='alert-danger')
            return HttpResponseRedirect(request.path)  
    if account_id:
        account = Account.objects.get(id=account_id)
    elif subaccount:
        account = subaccount.account
    else:
        account=None
        
    if request.method=='POST':
        
        if subaccount and request.POST:
            form = SubAccountForm(request.POST, instance=subaccount)

        else:
            form = SubAccountForm(request.POST)
        

        if form.is_valid():
            username = form.cleaned_data.get("username")
            ipn_mac_address = form.cleaned_data.get("ipn_mac_address")
            vpn_ip_address = form.cleaned_data.get("vpn_ip_address")
            ipn_ip_address = form.cleaned_data.get("ipn_ip_address")
            ipv4_vpn_pool = form.cleaned_data.get("ipv4_vpn_pool")
            ipv4_ipn_pool = form.cleaned_data.get("ipv4_ipn_pool")
            ipv6_vpn_pool = form.cleaned_data.get("ipv6_vpn_pool")
            vpn_ipv6_ip_address = form.cleaned_data.get("vpn_ipv6_ip_address")
            
    
    

    
            #print 111

            #print '1111111', subaccount, vpn_ipinuse, ipn_ipinuse, subaccount.ipv4_vpn_pool

                
            model =form.save(commit=False)

            model.save()
            log('EDIT', request.user, model) if id else log('CREATE', request.user, model) 
            messages.success(request, _(u'Субаккаунт сохранён.'), extra_tags='alert-success')
            return HttpResponseRedirect("%s?id=%s" % (reverse("subaccount"), model.id))
    
        else:
            if form._errors:
                for k, v in form._errors.items():
                    if str(k)=='__all__': k=''
                    messages.error(request, '%s %s' % (k, ','.join(v)), extra_tags='alert-danger')
            return {'subaccount': subaccount, 'account':account, "action_log_table":action_log_table, 'accountaddonservice_table':table,  'form':form}
    else:
        if  not (request.user.account.has_perm('billservice.view_subaccount')):
            messages.error(request, _(u'У вас нет прав на доступ в этот раздел.'), extra_tags='alert-danger')
            return HttpResponseRedirect('/ebsadmin/')
        if subaccount:
            
            form = SubAccountForm(instance=subaccount)
        else:
            form = SubAccountForm(initial={'account':account,})
        return {'subaccount': subaccount, 'account':account, "action_log_table":action_log_table, "accountaddonservice_table": table, 'form':form} 
    


@systemuser_required
@render_to('ebsadmin/accounthardware_edit.html')
def accounthardware(request):
    
    account = None
    account_id = request.POST.get("account_id")
    id = request.POST.get("id")
    item = None
    if request.method == 'POST': 
        id = request.POST.get('id')
        if id:
            item = AccountHardware.objects.get(id=id)
            form = AccountHardwareForm(request.POST, instance=item)
        else:
            form = AccountHardwareForm(request.POST)
        
        if  not (request.user.account.has_perm('billservice.change_account')):
            messages.error(request, _(u'У вас нет прав на редактирование аккаунтов'), extra_tags='alert-danger')
            return HttpResponseRedirect(request.path)


        
        
        if form.is_valid(): 
            model = form.save(commit=False)
            model.save()
            log('EDIT', request.user, model) if id else log('CREATE', request.user, model) 
            messages.success(request, _(u'Оборудование успешно добавлено.'), extra_tags='alert-success')
            return {'form':form,  'status': True} 
        else:

            return {'form':form,  'status': False} 
    else:
        id = request.GET.get("id")
        account_id = request.GET.get("account_id")
        if  not (request.user.account.has_perm('billservice.view_accounthardware')):
            messages.error(request, _(u'У вас нет прав на доступ в этот раздел.'), extra_tags='alert-danger')
            return HttpResponseRedirect("%s?id=%s" % (reverse("account_edit"),account_id))
        
        if id:
            item = AccountHardware.objects.get(id=id)
            form = AccountHardwareForm(instance=item)
        elif account_id:
            
            account= Account.objects.get(id=account_id)
            form = AccountHardwareForm(initial={'account': account, 'datetime': datetime.datetime.now()}) # An unbound form

    return { 'form':form, 'status': False, 'account':account, 'item': item} 

@systemuser_required
@render_to('ebsadmin/suspendedperiod/edit.html')
def suspendedperiod(request):
    
    account = None
    account_id = request.GET.get("account_id")
    id = request.POST.get("id")
    
    if request.method == 'POST': 

        form = SuspendedPeriodModelForm(request.POST) 
        if id:
            if  not (request.user.account.has_perm('billservice.change_suspendedperiod')):
                messages.error(request, _(u'У вас нет прав на редактирование периодов без списаний'), extra_tags='alert-danger')
                return {}
        else:
            if  not (request.user.account.has_perm('billservice.add_suspendedperiod')):
                messages.error(request, _(u'У вас нет прав на создание периодов без списаний'), extra_tags='alert-danger')
                return {}
        
        
        if form.is_valid(): 
            model = form.save(commit=False)
            model.save()
            log('EDIT', request.user, model) if id else log('CREATE', request.user, model) 
            return {'form':form,  'status': True} 
        else:

            return {'form':form,  'status': False} 
    else:
        id = request.GET.get("id")
        if  not (request.user.account.has_perm('billservice.view_accounthardware')):
            messages.error(request, _(u'У вас нет прав на доступ в этот раздел'), extra_tags='alert-danger')
            return {}
        if id:

            
            accounttariff = SuspendedPeriod.objects.get(id=id)
            form = SuspendedPeriodModelForm(instance=accounttariff)
        elif account_id:
            
            account= Account.objects.get(id=account_id)
            form = SuspendedPeriodModelForm(initial={'account': account.id, 'datetime': datetime.datetime.now()}) # An unbound form

    return { 'form':form, 'status': False, 'account':account} 

@systemuser_required
@render_to('ebsadmin/transaction_edit.html')
def transaction(request):
    
    account = None
    account_id = request.GET.get("account_id")
    id = request.POST.get("id")
    
    promise_type = TransactionType.objects.get(internal_name='PROMISE_PAYMENT')
    if request.method == 'POST': 

        form = TransactionModelForm(request.POST) 
        if id:
            if  not (request.user.account.has_perm('billservice.edit_transaction')):
                messages.error(request, _(u'У вас нет прав на изменение платежей'), extra_tags='alert-danger')
                return {}
        else:
            if  not (request.user.account.has_perm('billservice.add_transaction')):
                messages.error(request, _(u'У вас нет прав на создание платежей'), extra_tags='alert-danger')
                return {}
        form.fields["type"].queryset = request.user.account.transactiontype_set
        
        if form.is_valid(): 
            model = form.save(commit=False)
            model.systemuser = request.user.account
            model.save()
            log('EDIT', request.user, model) if id else log('CREATE', request.user, model) 
            messages.success(request, _(u'Операция выполнена.'), extra_tags='alert-success')
            return {'form':form,  'status': True, 'transaction': model} 
        else:
            messages.success(request, _(u'Ошибка при выполнении операции.'), extra_tags='alert-danger')
            return {'form':form,  'status': False, 'promise_type': promise_type} 
    else:
        id = request.GET.get("id")
        if  not (request.user.account.has_perm('billservice.view_transaction')):
            messages.error(request, _(u'У вас нет прав на просмотр проводок'), extra_tags='alert-danger')
            return {}
        if id:

            
            accounttariff = AccountTarif.objects.get(id=id)
            form = TransactionModelForm(instance=accounttariff)
        elif account_id:
            
            account= Account.objects.get(id=account_id)
        now = datetime.datetime.now()
        form = TransactionModelForm(initial={'account': account.id, 'created': now, 'type': TransactionType.objects.get(internal_name='MANUAL_TRANSACTION')}) # An unbound form
        form.fields["type"].queryset = request.user.account.transactiontype_set
    return { 'form':form, 'status': False, 'account':account, 'promise_type': promise_type} 


@systemuser_required
@render_to('ebsadmin/accountaddonservice_edit.html')
def accountaddonservice_edit(request):
    
    account = None
    account_id = request.GET.get("account_id")
    subaccount_id = request.GET.get("subaccount_id")
    id = request.GET.get("id")
    accountaddonservice = None
    if request.method == 'POST': 
        if id:

            model = AccountAddonService.objects.get(id=id)
            form = AccountAddonServiceModelForm(request.POST, instance=model) 
            if  not (request.user.account.has_perm('billservice.change_accountaddonservice')):
                messages.error(request, _(u'У вас нет прав на редактирование привязок подключаемых услуг'), extra_tags='alert-danger')
                return {}

        else:
            form = AccountAddonServiceModelForm(request.POST) 
            if  not (request.user.account.has_perm('billservice.add_accountaddonservice')):
                messages.error(request, _(u'У вас нет прав на создание привязок подключаемых услуг'), extra_tags='alert-danger')
                return {}


        if form.is_valid():
            model = form.save(commit=False)
            model.save()
            log('EDIT', request.user, model) if id else log('CREATE', request.user, model) 
            messages.success(request, _(u'Услуга добавлена.'), extra_tags='alert-success')
            return {'form':form,  'status': True} 
        else:
            messages.error(request, _(u'Услуга не добавлена.'), extra_tags='alert-danger')
            return {'form':form,  'status': False} 
    else:
        id = request.GET.get("id")
        if  not (request.user.account.has_perm('billservice.view_addonservice')):
            messages.error(request, _(u'У вас нет прав на просмотр  подключаемых услуг'), extra_tags='alert-danger')
            return {}
        if id:


            accountaddonservice = AccountAddonService.objects.get(id=id)
            
            form = AccountAddonServiceModelForm(instance=accountaddonservice)
        elif account_id:

            account= Account.objects.get(id=account_id)
            form = AccountAddonServiceModelForm(initial={'account': account, 'activated': datetime.datetime.now()}) # An unbound form
        elif subaccount_id:
            subaccount= SubAccount.objects.get(id=subaccount_id)
            account= subaccount.account
            form = AccountAddonServiceModelForm(initial={'account': account, 'subaccount': subaccount, 'activated': datetime.datetime.now()}) # An unbound form

    return { 'form':form, 'status': False, 'account':account, "accountaddonservice":accountaddonservice} 

@systemuser_required
@render_to('ebsadmin/template/select_window.html')
def templateselect(request):
    if  not (request.user.account.has_perm('billservice.view_template')):
        messages.error(request, _(u'У вас нет прав на просмотр списка шаблонов'), extra_tags='alert-danger')
        return {}
    types = request.GET.getlist('type')
    form = TemplateSelectForm()
    form.fields['template'].queryset=Template.objects.filter(type__id__in=types)
    return { 'form':form} 




@systemuser_required
@render_to('ebsadmin/activesession_list.html')
def activesessionreport(request):
    if  not (request.user.account.has_perm('radius.view_activesession')):
        messages.error(request, _(u'У вас нет прав на доступ в этот раздел.'), extra_tags='alert-danger')
        return HttpResponseRedirect('/ebsadmin/')
    if request.GET:
        form = SessionFilterForm(request.GET)
        if form.is_valid():
            account_text = request.GET.get('account_text')
            res = ActiveSession.objects.prefetch_related()
            if form.cleaned_data.get("account"):
                res = res.filter(account__in=form.cleaned_data.get("account"))

            if form.cleaned_data.get("date_start"):
                res = res.filter(date_start__gte=form.cleaned_data.get("date_start"))

            if form.cleaned_data.get("date_end"):
                res = res.filter(date_end__lte=form.cleaned_data.get("date_end"))

            if form.cleaned_data.get("city"):
                res = res.filter(account__city=form.cleaned_data.get("city"))

            if form.cleaned_data.get("street"):
                res = res.filter(account__street=form.cleaned_data.get("street"))

            if form.cleaned_data.get("house"):
                res = res.filter(account__house=form.cleaned_data.get("house"))
                
            if form.cleaned_data.get("only_active"):
                res = res.filter(session_status='ACTIVE')
            if account_text:
                res = res.filter(Q(account__username__startswith=account_text) | Q(account__contract__startswith=account_text) )
            

            if form.cleaned_data.get("nas"):
                res = res.filter(nas_int__in=form.cleaned_data.get("nas"))
            res = res.values('id', 'subaccount__username', 'subaccount', 'framed_ip_address', 'interrim_update', 'framed_protocol', 'bytes_in', 'bytes_out', 'date_start', 'date_end', 'session_status', 'caller_id', 'nas_int__name', 'session_time', 'account__street', 'account__house', 'account__room')
            table = ActiveSessionTable(res)
            table_to_report = RequestConfig(request, paginate=False if request.GET.get('paginate')=='False' else True).configure(table)
            if table_to_report:
                return create_report_http_response(table_to_report, request)
    
            return {"table": table,  'form':form}   
    
        else:
    
            return {'form':form}
    else:
        table = None
        res = ActiveSession.objects.filter(session_status='ACTIVE').prefetch_related()
        res = res.values('id', 'subaccount__username', 'subaccount', 'framed_ip_address',  'interrim_update', 'framed_protocol', 'bytes_in', 'bytes_out', 'date_start', 'date_end', 'session_status', 'caller_id', 'nas_int__name', 'session_time', 'account__street', 'account__house', 'account__room')
        table = ActiveSessionTable(res)
        table_to_report = RequestConfig(request, paginate=False if request.GET.get('paginate')=='False' else True).configure(table)
        if table_to_report:
            return create_report_http_response(table_to_report, request)
    
        form = SessionFilterForm(initial={'only_active': True})
        return {"table": table, 'form':form, "table": table,} 


@systemuser_required
@render_to('ebsadmin/common/list.html')
def template(request):
    if  not (request.user.account.has_perm('billservice.view_template')):
        messages.error(request, _(u'У вас нет прав на доступ в этот раздел.'), extra_tags='alert-danger')
        return HttpResponseRedirect('/ebsadmin/')
    
    res = Template.objects.all()
    table = TemplateTable(res)
    table_to_report = RequestConfig(request, paginate=True if not request.GET.get('paginate')=='False' else False).configure(table)
    if table_to_report:
        return create_report_http_response(table_to_report, request)
    return {
        "list_url": reverse('template'),
        "list_header": _(u'Шаблоны документов'),
        "add_btn_url": reverse('template_edit'),
        "table": table
    }
    
@systemuser_required
@render_to('ebsadmin/template/edit.html')
def template_edit(request):

    id = request.GET.get("id")
    item = None
    if id:


        item = Template.objects.get(id=id)
        
            
    if request.method == 'POST': 
        if item:
            form = TemplateForm(request.POST, instance=item)
        else:
            form = TemplateForm(request.POST)
        if id:
            if  not (request.user.account.has_perm('billservice.change_template')):
                messages.error(request, _(u'У вас нет прав на редактирование iшаблонов документов'), extra_tags='alert-danger')
                return HttpResponseRedirect(request.path)
            
        else:
            if  not (request.user.account.has_perm('billservice.add_template')):
                messages.error(request, _(u'У вас нет прав на создание iшаблонов документов'), extra_tags='alert-danger')
                return HttpResponseRedirect(request.path)

        
        if form.is_valid():
 
            model = form.save(commit=False)
            model.save()
            log('EDIT', request.user, model) if id else log('CREATE', request.user, model) 
            return HttpResponseRedirect(reverse("template"))
        else:

            return { 'form':form, 'template': item} 
    else:
        if  not (request.user.account.has_perm('billservice.view_template')):
            messages.error(request, _(u'У вас нет прав на доступ в этот раздел.'), extra_tags='alert-danger')
            return HttpResponseRedirect('/ebsadmin/')
        if item:
            form = TemplateForm(instance=item)
        else:
            form = TemplateForm()

   
    return { 'form':form, 'template': item} 

@ajax_request
@systemuser_required
def subaccount_delete(request):
    if  not (request.user.account.has_perm('billservice.delete_subaccount')):
        return {'status':True, 'message': _(u'У вас нет прав на удаление субаккаунта')}
    id = request.POST.get('id') or request.GET.get('id')
    if id:
        #TODO: СДелать удаление субаккаунта с сервера доступа, если он там был
        item = SubAccount.objects.get(id=id)
        if item.vpn_ipinuse:
            log('DELETE', request.user, item.vpn_ipinuse)
            item.vpn_ipinuse.delete()

        if item.ipn_ipinuse:
            log('DELETE', request.user, item.ipn_ipinuse)
            item.ipn_ipinuse.delete()

        if item.vpn_ipv6_ipinuse:
            log('DELETE', request.user, item.vpn_ipv6_ipinuse)
            item.vpn_ipv6_ipinuse.delete()
        
        log('DELETE', request.user, item)
        if item.ipn_added:
            subaccount_ipn_delete(item.account, item, item.nas, 'IPN')
        item.delete()
        
        messages.success(request, _(u'Субаккаунт удалён.'), extra_tags='alert-success')
        return {"status": True}
    else:
        return {"status": False, "message": "SubAccount not found"}
    
@ajax_request
@systemuser_required
def accounttariff_delete(request):
    if  not (request.user.account.has_perm('billservice.delete_accounttarif')):
        return {'status':False, 'message': _(u'У вас нет прав на удаление связки тарифа')}
    id = int(request.POST.get('id',0)) or int(request.GET.get('id',0))
    if id:
        try:
            item = AccountTarif.objects.get(id=id)
        except Exception, e:
            return {"status": False, "message": _(u"Указанный тарифный план не найден тарифный план %s") % str(e)}
        if item.datetime<datetime.datetime.now():
            return {"status": False, "message": _(u"Невозможно удалить вступивший в силу тарифный план")}
        log('DELETE', request.user, item)
        item.delete()
        messages.success(request,_( u'Тарифный план применён.'), extra_tags='alert-success')
        return {"status": True}
    else:
        messages.error(request, _(u'Ошибка при изменении тарифного плана.'), extra_tags='alert-danger')
        return {"status": False, "message": "AccountTarif not found"}
    
@ajax_request
@systemuser_required
def accounthardware_delete(request):
    if  not (request.user.account.has_perm('billservice.delete_accounthardware')):
        return {'status':False, 'message': _(u'У вас нет прав на удаление оборудования аккаунта')}
    id = int(request.POST.get('id',0)) or int(request.GET.get('id',0))
    if id:
        model = AccountHardware.objects.get(id=id)
        log('DELETE', request.user, model)
        model.delete()
        return {"status": True}
    else:
        return {"status": False, "message": "AccountHardware not found"}

@ajax_request
@systemuser_required
def accountaddonservice_deactivate(request):
    if  not (request.user.account.has_perm('billservice.change_accountaddonservice')):
        return {'status':False, 'message': _(u'У вас нет прав на изменение подключаемых услуг аккаунта')}
    id = int(request.POST.get('id',0)) or int(request.GET.get('id',0))
    if id:
        model = AccountAddonService.objects.get(id=id)
        log('DELETE', request.user, model)
        model.deactivated = datetime.datetime.now()
        model.save()
        return {"status": True}
    else:
        return {"status": False, "message": "AccountAddonService not found"}
    
@ajax_request
@systemuser_required
def accountaddonservice_delete(request):
    if  not (request.user.account.has_perm('billservice.delete_accountaddonservice')):
        return {'status':False, 'message': _(u'У вас нет прав на удаление подключаемых услуг аккаунта')}
    id = int(request.POST.get('id',0)) or int(request.GET.get('id',0))
    if id:
        model = AccountAddonService.objects.get(id=id)
        log('DELETE', request.user, model)
        model.delete()
        return {"status": True}
    else:
        return {"status": False, "message": "AccountAddonService not found"}
    
@ajax_request
@systemuser_required
def suspendedperiod_delete(request):
    if  not (request.user.account.has_perm('billservice.delete_suspendedperiod')):
        return {'status':False, 'message': _(u'У вас нет прав на удаление периода простоя')}
    id = int(request.POST.get('id',0)) or int(request.GET.get('id',0))
    if id:
        try:
            item = SuspendedPeriod.objects.get(id=id)
        except Exception, e:
            return {"status": False, "message": _(u"Указанный период не найден %s") % str(e)}
        log('DELETE', request.user, item)
        item.delete()
        return {"status": True}
    else:
        return {"status": False, "message": "SuspendedPeriod not found"} 
    
@ajax_request
@systemuser_required
def template_delete(request):
    if  not (request.user.account.has_perm('billservice.delete_template')):
        return {'status':False, 'message': _(u'У вас нет прав на удаление шаблонов')}
    id = int(request.POST.get('id',0)) or int(request.GET.get('id',0))
    if id:
        try:
            item = Template.objects.get(id=id)
        except Exception, e:
            return {"status": False, "message": _(u"Указанный шаблон не найден %s") % str(e)}
        log('DELETE', request.user, item)
        item.delete()
        return {"status": True}
    else:
        return {"status": False, "message": "Template not found"} 
    
@ajax_request
@systemuser_required
def totaltransaction_delete(request):
    if  not (request.user.account.has_perm('billservice.delete_transaction')):
        return {'status':False, 'message': _(u'У вас нет прав на удаление проводок')}
    transactions = request.POST.getlist('transactions')
    print transactions
    if transactions:
        try:
            for item in transactions:
                print item
                table, tr_id = item.split('__')
                model = model_by_table.get(table)
                item = model.objects.get(id=tr_id)
                log('DELETE', request.user, item)
                item.delete()
        except Exception, e:
            print e
            return {"status": False, "message": _(u"Указанные проводки не найдены %s") % str(e)}

        return {"status": True}
    else:
        return {"status": False, "message": "Transaction not found"} 

    