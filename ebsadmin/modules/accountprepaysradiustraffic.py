# -*-coding: utf-8 -*-

from ebscab.lib.decorators import render_to, ajax_request
from django.contrib.auth.decorators import login_required
from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect
from django_tables2_reports.config import RequestConfigReport as RequestConfig
from django_tables2_reports.utils import create_report_http_response
from object_log.models import LogItem

from ebsadmin.tables import AccountPrepaysRadiusTraficTable
from billservice.forms import AccountPrepaysRadiusTraficSearchForm, AccountPrepaysRadiusTraficForm
from billservice.models import AccountPrepaysRadiusTrafic
from django.contrib import messages
log = LogItem.objects.log_action



@login_required
@render_to('ebsadmin/accountprepaysradiustraffic_list.html')
def accountprepaysradiustraffic(request):
        

    if not request.user.account.has_perm('billservice.view_accountprepaysradiustraffic'):
        messages.error(request, u'У вас нет прав на доступ в этот раздел.', extra_tags='alert-danger')
        return HttpResponseRedirect('/ebsadmin/')

    if request.method=='GET' and request.GET: 
        data = request.GET

        #pageitems = 100
        form = AccountPrepaysRadiusTraficSearchForm(data)
        if form.is_valid():
            
            account = form.cleaned_data.get('account')
            current = form.cleaned_data.get('current')
            tariff = form.cleaned_data.get('tariff')
            daterange = form.cleaned_data.get('daterange') or []
            start_date, end_date = None, None
            if daterange:
                start_date = daterange[0]
                end_date = daterange[1]
            
            
            
            res = AccountPrepaysRadiusTrafic.objects.all().order_by('account_tarif__account', 'current')
            if account:
                res = res.filter(account_tarif__account__id__in=account)


            if tariff:
                res = res.filter(account_tarif__tarif__in=tariff)
                
            if current:
                res = res.filter(current=current)
                
            if start_date:
                res = res.filter(datetime__gte=start_date)
            if end_date:
                res = res.filter(datetime__lte=end_date)
                
            table = AccountPrepaysRadiusTraficTable(res)
            table_to_report = RequestConfig(request, paginate=True if not request.GET.get('paginate')=='False' else False).configure(table)
            if table_to_report:
                return create_report_http_response(table_to_report, request)
            
            return {"table": table,  'form':form, 'resultTab':True}   
    
        else:
            return {'status':False, 'form':form}
    else:
        form = AccountPrepaysRadiusTraficSearchForm()
        return { 'form':form}   

@login_required
@render_to('ebsadmin/accountprepaysradiustraffic_edit.html')
def accountprepaysradiustraffic_edit(request):
    id = request.POST.get("id")

    item = None

    if request.method == 'POST': 

        if id:
            model = AccountPrepaysRadiusTrafic.objects.get(id=id)
            form = AccountPrepaysRadiusTraficForm(request.POST, instance=model) 
            if  not (request.user.account.has_perm('billservice.change_accountprepaysradiustraffic')):
                messages.error(request, u'У вас нет прав на редактирование предоплаченного RADIUS трафика', extra_tags='alert-danger')
                return HttpResponseRedirect(request.path)
        else:
            form = AccountPrepaysRadiusTraficForm(request.POST) 
        if  not (request.user.account.has_perm('billservice.add_accountprepaysradiustraffic')):
            messages.error(request, u'У вас нет прав на добавление RADIUS предоплаченного трафика.', extra_tags='alert-danger')
            return HttpResponseRedirect(request.path)


        if form.is_valid():
            model = form.save(commit=False)
            model.save()

            log('EDIT', request.user, model) if id else log('CREATE', request.user, model) 
            return {'form':form,  'status': True} 
        else:

            return {'form':form,  'status': False} 
    else:
        id = request.GET.get("id")

        if  not (request.user.account.has_perm('billservice.view_accountprepaysradiustraffic')):
            messages.error(request, u'У вас нет прав на доступ в этот раздел.', extra_tags='alert-danger')
            return {'status': False}
            
        if id:
            item = AccountPrepaysRadiusTrafic.objects.get(id=id)
            
            form = AccountPrepaysRadiusTraficForm(instance=item)
        else:
            form = AccountPrepaysRadiusTraficForm()

    return { 'form':form, 'status': False} 

@ajax_request
@login_required
def accountprepaysradiustraffic_delete(request):
    if  not (request.user.account.has_perm('billservice.delete_accountprepaysradiustrafic')):
        return {'status':False, 'message': u'У вас нет прав на удаление предоплаченного NetFlow трафика'}
    id = int(request.POST.get('id',0)) or int(request.GET.get('id',0))
    if id:
        try:
            item = AccountPrepaysRadiusTrafic.objects.get(id=id)
        except Exception, e:
            return {"status": False, "message": u"Указанная запись не найдена %s" % str(e)}
        log('DELETE', request.user, item)
        item.delete()
        return {"status": True}
    else:
        return {"status": False, "message": "AccountPrepaysRadiusTrafic not found"} 
    