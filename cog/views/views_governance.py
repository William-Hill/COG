from cog.forms import *
from cog.models import *
from cog.models.constants import LEAD_ORGANIZATIONAL_ROLES_DICT, \
    ROLE_CATEGORY_LEAD, ROLE_CATEGORY_MEMBER, MANAGEMENT_BODY_CATEGORY_STRATEGIC, \
    MANAGEMENT_BODY_CATEGORY_OPERATIONAL
from constants import PERMISSION_DENIED_MESSAGE
from django.contrib.auth.decorators import login_required
from django.forms.models import BaseInlineFormSet, modelformset_factory, \
    inlineformset_factory
from django.http import HttpResponseRedirect, HttpResponse, \
    HttpResponseForbidden
from django.shortcuts import get_object_or_404, render_to_response
from django.template import RequestContext
from django.utils.functional import curry
from views_project import getProjectNotActiveRedirect, \
    getProjectNotVisibleRedirect

def _hasGovernanceInfo(project, tab):
    '''Utility function to determine whether a project has been populated 
       with the requested type of governance object.'''
    
    if tab=='bodies':
        if len(project.managementbody_set.all()) > 0:
            return True
    elif tab == 'roles':
        if len(getLeadOrganizationalRoles(project)) > 0 or len(getMemberOrganizationalRoles(project)) > 0:
            return True
    elif tab == 'processes':
        if len(project.communicationmeans_set.all()) > 0 \
        or project.taskPrioritizationStrategy is not None \
        or project.requirementsIdentificationProcess is not None\
        or len(project.policies()) > 0:
            return True
    return False

def governance_display(request, project_short_name, tab):
    ''' Dispatcher for governance view pages. '''
    
    project = get_object_or_404(Project, short_name__iexact=project_short_name)
    
    # check project is active
    if project.active==False:
        return getProjectNotActiveRedirect(request, project)
    elif project.isNotVisible(request.user):
        return getProjectNotVisibleRedirect(request, project)
    
    # selective display parameter
    #display = request.GET.get('display','ALL')
    
    # build list of children with governance info that are visible to user
    children = []
    for child in project.children():
        if _hasGovernanceInfo(child, tab) and child.isVisible(request.user):
            children.append(child)
    
    # build list of peers with governance info that are visible to user
    peers = []
    for peer in project.peers.all():
        if _hasGovernanceInfo(peer, tab) and peer.isVisible(request.user):
            peers.append(peer)
    
    template_page = 'cog/governance/_governance.html'
    template_title = 'Governance %s' % tab.capitalize()
    template_form_name = None
    return render_to_response('cog/common/rollup.html', 
                              {'project': project, 'title': '%s %s' % (project.short_name, template_title), 
                               'template_page': template_page, 'template_title': template_title, 'template_form_name':template_form_name,
                               'children':children, 'peers':peers,
                               'tab':tab },
                              context_instance=RequestContext(request))

# view to update the project Management Body objects
@login_required
def management_body_update(request, project_short_name, category):
    
    # initialize ManagementBodyPurpose choices
    if len(ManagementBodyPurpose.objects.all())==0:
        initManagementBodyPurpose()
        
    # use different forms to limit selection of ManagementBodyPurpose
    if category==MANAGEMENT_BODY_CATEGORY_STRATEGIC:
        objectTypeForm = StrategicManagementBodyForm
        formsetType = StrategicManagementBodyInlineFormset
    else:
        objectTypeForm = OperationalManagementBodyForm
        formsetType = OperationalManagementBodyInlineFormset
    
    # delegate to view for generic governance object
    tab = 'bodies'
    return governance_object_update(request, project_short_name, tab, ManagementBody, objectTypeForm, formsetType,
                                    '%s Management Bodies Update' % category, 'cog/governance/management_body_form.html')

# view to update the project Communication Means objects
@login_required
def communication_means_update(request, project_short_name):

    # delegate to view for generic governance object
    tab = 'processes'
    return governance_object_update(request, project_short_name, tab, CommunicationMeans, CommunicationMeansForm, BaseInlineFormSet,
                                    'Communication and Coordination Update', 'cog/governance/communication_means_form.html')

    
# Subclass of BaseInlineFormset that is used to 
# sub-select the 'strategic' instances of ManagementBody specific to a given project
class StrategicManagementBodyInlineFormset(BaseInlineFormSet):
        
    def get_queryset(self):
        # standard BaseInlineFormSet that sub-selects by instance=project
        querySet = super(StrategicManagementBodyInlineFormset, self ).get_queryset() 
        # additionally sub-select by category='Strategic'
        return querySet.filter(category='Strategic')
    
class OperationalManagementBodyInlineFormset(BaseInlineFormSet):
        
    def get_queryset(self):
        return  super(OperationalManagementBodyInlineFormset, self ).get_queryset().filter(category='Operational')
        
# Generic view for updating a governance object.
#
# The object must have the following attributes and methods:
# obj.project
# obj.__unicode__
def governance_object_update(request, project_short_name, tab, objectType, objectTypeForm, formsetType, title, template):
    
    # retrieve project from database
    project = get_object_or_404(Project, short_name__iexact=project_short_name)
    
    # check permission
    if not userHasAdminPermission(request.user, project):
        return HttpResponseForbidden(PERMISSION_DENIED_MESSAGE)
    
    # initialize formset factory for this governance object
    ObjectFormSet  = inlineformset_factory(Project, objectType, extra=1, form=objectTypeForm, formset=formsetType)

    # GET request
    if (request.method=='GET'):
        
        # create formset instance associated to current project
        formset = ObjectFormSet(instance=project)
        
        return render_governance_object_form(request, project, formset, title, template)

    # POST method
    else:
        # update formset from POST data
        formset = ObjectFormSet(request.POST, instance=project)
        
        if formset.is_valid():
            
            # save changes to databaase
            instances = formset.save()
            
            # set the object category from the other fields, save again
            for instance in instances:
                instance.set_category()
                       
            # redirect to governance display (GET-POST-REDIRECT)
            return HttpResponseRedirect(reverse('governance_display', args=[project.short_name.lower(), tab]))
            
        else:
            print 'Formset is invalid  %s' % formset.errors
            return render_governance_object_form(request, project, formset, title, template)
            

def render_governance_object_form(request, project, formset, title, template):
    return render_to_response(template,
                              {'title' : title, 'project':project, 'formset':formset },
                              context_instance=RequestContext(request))

# view to update a Management Body object members
@login_required
def management_body_members(request, project_short_name, object_id):
    
    # retrieve object
    managementBody = get_object_or_404(ManagementBody, pk=object_id)
    
    # create form class with current project
    managementBodyMemberForm = staticmethod(curry(ManagementBodyMemberForm, project=managementBody.project))
    
    # delegate to generic view with specific object types
    tab = 'bodies'
    return members_update(request, tab, object_id, ManagementBody, ManagementBodyMember, managementBodyMemberForm)
  
# view to update a Communication Means object members  
@login_required
def communication_means_members(request, object_id):
    
    commnicationMeans = get_object_or_404(CommunicationMeans, pk=object_id)
    # create form class with current project
    communicationMeansMemberForm = staticmethod(curry(CommunicationMeansMemberForm, project=commnicationMeans.project))
    
    # delegate to generic view with specific object types
    tab = 'processes'
    return members_update(request, tab, object_id, CommunicationMeans, CommunicationMeansMember, communicationMeansMemberForm)

# view to update an Organizational Role object members  
@login_required
def organizational_role_members(request, object_id):
    
    organizationalRole = get_object_or_404(OrganizationalRole, pk=object_id)

    # create form class with current project
    organizationalRoleMemberForm = staticmethod(curry(OrganizationalRoleMemberForm, project=organizationalRole.project))
    
    # delegate to generic view with specific object types
    tab = 'roles'
    return members_update(request, tab, object_id, OrganizationalRole, OrganizationalRoleMember, organizationalRoleMemberForm)

# 
# Generic view to update members for:
# -) objectType=CommunicationMeans, objectMemberType=CommunicationMeansMember
# -) objectType=ManagementBody, objectMemberType=ManagementBodyMember
#
# The object must have the following attributes and methods:
# obj.project
# obj.__unicode__
#
def members_update(request, tab, objectId, objectType, objectMemberType, objectForm):
    
    # retrieve governance object
    obj = get_object_or_404(objectType, pk=objectId)
    
    # check permission
    if not userHasAdminPermission(request.user, obj.project):
        return HttpResponseForbidden(PERMISSION_DENIED_MESSAGE)
    
    # formset factory
    ObjectFormSet  = inlineformset_factory(objectType, objectMemberType, extra=3)
    # set the formset form to custom class that includes the current project
    ObjectFormSet.form = objectForm
    
    
    # GET request
    if request.method=='GET':
        
        # retrieve current members
        formset = ObjectFormSet(instance=obj)
        
        # render view
        return render_members_form(request, obj, formset)
        
    # POST request
    else:
        formset = ObjectFormSet(request.POST, instance=obj)
        
        if formset.is_valid():
            
            # save updated members
            instances = formset.save()
            
            # redirect to governance display (GET-POST-REDIRECT)
            return HttpResponseRedirect(reverse('governance_display', args=[obj.project.short_name.lower(), tab]))
          
        else:
            print 'Formset is invalid: %s' % formset.errors
            
            # redirect to form view
            return render_members_form(request, obj, formset)
        
def render_members_form(request, object, formset):
        
    return render_to_response('cog/governance/members_form.html',
                              {'title' : '%s Members Update' % object, 
                               'project': object.project,
                               'formset':formset },
                               context_instance=RequestContext(request))
    
@login_required
def govprocesses_update(request, project_short_name):
    
    # retrieve project from database
    project = get_object_or_404(Project, short_name__iexact=project_short_name)
    
    # check permission
    if not userHasAdminPermission(request.user, project):
        return HttpResponseForbidden(PERMISSION_DENIED_MESSAGE)
    
    # GET request
    if request.method=='GET':
                
        # create form object from model
        form = GovernanceProcessesForm(instance=project)

        # render form
        return render_governance_processes_form(request, form, project)
    
    # POST request
    else:
        
        # update object from form data
        form = GovernanceProcessesForm(request.POST, instance=project)
        
        # validate form data
        if form.is_valid():
            
            # persist changes
            project = form.save()
            
            # redirect to governance display (GET-POST-REDIRECT)
            tab = 'processes'
            return HttpResponseRedirect(reverse('governance_display', args=[project.short_name.lower(), tab]))            
            
        # return to form
        else:
            print 'Form is invalid %s' % form.errors
            return render_governance_processes_form(request, form, project)

def render_governance_processes_form(request, form, project):
    return render_to_response('cog/governance/governance_processes_form.html',
                              {'title' : 'Governance Processes Update', 'project': project, 'form':form },
                               context_instance=RequestContext(request))
    
# Method to update an organizationl role
@login_required
def organizational_role_update(request, project_short_name):
    
    # retrieve project from database
    project = get_object_or_404(Project, short_name__iexact=project_short_name)
    
    # check permission
    if not userHasAdminPermission(request.user, project):
        return HttpResponseForbidden(PERMISSION_DENIED_MESSAGE)
    
    # must build the formset via non-traditional means to pass the current project as a class attribute
    OrganizationalRoleFormSet  = inlineformset_factory(Project, OrganizationalRole, extra=1, can_delete=True, form=OrganizationalRoleForm)
    
    # GET request
    if request.method=='GET':
        # create formset backed up by current saved instances
        organizational_role_formset = OrganizationalRoleFormSet(instance=project)
        
        # display form view
        return render_organizational_role_form(request, project, organizational_role_formset)
        
    # POST request
    else:
        organizational_role_formset = OrganizationalRoleFormSet(request.POST, instance=project)
        
        # validate formset
        if organizational_role_formset.is_valid():
            
            # save changes to databaase
            orgrole_instances = organizational_role_formset.save()
            
            # assign role category and save again
            for role in orgrole_instances:
                role.set_category()
            
            # redirect to governance display (GET-POST-REDIRECT)
            tab = 'roles'
            return HttpResponseRedirect(reverse('governance_display', args=[project.short_name.lower(), tab]))
            
        else:
            print 'Organizational Role formset is invalid: %s' % organizational_role_formset.errors
            
            # redorect to form
            return render_organizational_role_form(request, project, organizational_role_formset)
    
def render_organizational_role_form(request, project, formset):
    return render_to_response('cog/governance/organizational_role_form.html',
                              {'title' : 'Organizational Roles Update', 'project':project, 'formset':formset },
                              context_instance=RequestContext(request))
