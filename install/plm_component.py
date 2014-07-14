# -*- encoding: utf-8 -*-
##############################################################################
#
#    OmniaSolutions, Your own solutions
#    Copyright (C) 2010 OmniaSolutions (<http://omniasolutions.eu>). All Rights Reserved
#    $Id$
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################
import os
import time
import types
from tools.translate import _
from osv import osv, fields
from datetime import datetime
import logging

#USED_STATES=[('draft','Draft'),('confirmed','Confirmed'),('released','Released'),('undermodify','UnderModify'),('obsoleted','Obsoleted')]
#STATEFORRELEASE=['confirmed']
#STATESRELEASABLE=['confirmed','transmitted','released','undermodify','obsoleted']

class plm_component(osv.osv):
    _inherit = 'product.product'
    _columns = {
                'create_date': fields.datetime('Date Created', readonly=True),
                'write_date': fields.datetime('Date Modified', readonly=True),
    }

#   Internal methods
           
    def _getbyrevision(self, cr, uid, name, revision):
        result=None
        results=self.search(cr,uid,[('engineering_code','=',name),('engineering_revision','=',revision)])
        for result in results:
            break
        return result

    def _getExplodedBom(self, cr, uid, ids, level=0, currlevel=0):
        """
            Return a flat list of all children in a Bom ( level = 0 one level only, level = 1 all levels)
        """
        result=[]
        if level==0 and currlevel>1:
            return result
        components=self.pool.get('product.product').browse(cr, uid, ids)
        relType=self.pool.get('mrp.bom')
        for component in components: 
            for bomid in component.bom_ids:
                children=relType.GetExplodedBom(cr, uid, [bomid.id], level, currlevel)
                result.extend(children)
        return result

    def _getChildrenBom(self, cr, uid, component, level=0, currlevel=0, context=None):
        """
            Return a flat list of each child, listed once, in a Bom ( level = 0 one level only, level = 1 all levels)
        """
        result=[]
        bufferdata=[]
        if level==0 and currlevel>1:
            return bufferdata
        for bomid in component.bom_ids:
            for bom in bomid.bom_lines:
                children=self._getChildrenBom(cr, uid, bom.product_id, level, currlevel+1, context=context)
                bufferdata.extend(children)
                bufferdata.append(bom.product_id.id)
        result.extend(bufferdata)
        return list(set(result))

    def getLastTime(self, cr, uid, oid, default=None, context=None):
        return self.getUpdTime(self.browse(cr, uid, oid, context=context))

    def getUpdTime(self, obj):
        if(obj.write_date!=False):
            return datetime.strptime(obj.write_date,'%Y-%m-%d %H:%M:%S')
        else:
            return datetime.strptime(obj.create_date,'%Y-%m-%d %H:%M:%S')

##  Customized Automations
    def on_change_name(self, cr, uid, oid, name=False, engineering_code=False):
        if name:
            results=self.search(cr,uid,[('name','=',name)])
            if len(results) > 0:
                raise osv.except_osv(_('Update Part Warning'), _("Part %s already exists.\nClose with OK to reuse, with Cancel to discharge." %(name)))
            if not engineering_code:
                return {'value': {'engineering_code': name}}            
        return {}

##  External methods
    def Clone(self, cr, uid, oid, default=None, context=None):
        """
            create a new revision of the component
        """
        defaults={}
        exitValues={}
        newID=self.copy(cr,uid,oid,defaults,context)
        if newID != None:
            newEnt=self.browse(cr,uid,newID,context=context)
            exitValues['_id']=newID
            exitValues['name']=newEnt.name
            exitValues['engineering_code']=newEnt.engineering_code
            exitValues['engineering_revision']=newEnt.engineering_revision
            exitValues['engineering_writable']=True
            exitValues['state']='draft'
        return exitValues

    def newVersion(self,cr,uid,ids,context=None):
        """
            create a new version of the component (to WorkFlow calling)
        """
        if self.newRevision(cr,uid,ids,context=context)!=None:
            return True 
        return False

    def GetUpdated(self,cr,uid,vals,context=None):
        """
            Get Last/Requested revision of given items (by name, revision, update time)
        """
        partData, attribNames = vals
        ids=self.GetLatestIds(cr, uid, partData, context)
        return self.read(cr, uid, list(set(ids)), attribNames)

    def GetLatestIds(self,cr,uid,vals,context=None):
        """
            Get Last/Requested revision of given items (by name, revision, update time)
        """
        ids=[]
        for partName, partRev, updateDate in vals:
            if updateDate:
                if partRev == None or partRev == False:
                    partIds=self.search(cr,uid,[('engineering_code','=',partName),('write_date','>',updateDate)],order='engineering_revision',context=context)
                    if len(partIds)>0:
                        ids.append(partIds[len(partIds)-1])
                else:
                    ids.extend(self.search(cr,uid,[('engineering_code','=',partName),('engineering_revision','=',partRev),('write_date','>',updateDate)],context=context))
            else:
                if partRev == None or partRev == False:
                    partIds=self.search(cr,uid,[('engineering_code','=',partName)],order='engineering_revision',context=context)
                    if len(partIds)>0:
                        ids.append(partIds[len(partIds)-1])
                else:
                    ids.extend(self.search(cr,uid,[('engineering_code','=',partName),('engineering_revision','=',partRev)],context=context))
        return list(set(ids))
    
    def NewRevision(self,cr,uid,ids,context=None):
        """
            create a new revision of current component
        """
        newID=None
        newIndex=0
        for oldObject in self.browse(cr, uid, ids, context=context):
            newIndex=int(oldObject.engineering_revision)+1
            defaults={}
            defaults['engineering_writable']=False
            defaults['state']='undermodify'
            self.write(cr, uid, [oldObject.id], defaults, context=context, check=False)
            # store updated infos in "revision" object
            defaults['name']=oldObject.name                 # copy function needs an explicit name value
            defaults['engineering_revision']=newIndex
            defaults['engineering_writable']=True
            defaults['state']='draft'
            defaults['linkeddocuments']=[]                  # Clean attached documents for new revision object
            newID=self.copy(cr, uid, oldObject.id, defaults, context=context)
            # create a new "old revision" object
            break
        return (newID, newIndex) 

    def SaveOrUpdate(self, cr, uid, vals, default=None, context=None):
        """
            Save or Update Parts
        """
        listedParts=[]
        retValues=[]
        for part in vals:
            hasSaved=False
            if part['engineering_code'] in listedParts:
                continue
            if not ('engineering_code' in part) or (not 'engineering_revision' in part):
                part['componentID']=False
                part['hasSaved']=hasSaved
                continue
            existingID=self.search(cr,uid,[
                                           ('engineering_code','=',part['engineering_code'])
                                          ,('engineering_revision','=',part['engineering_revision'])])
            if not existingID:
                existingID=self.create(cr,uid,part)
                hasSaved=True
            else:
                existingID=existingID[0]
                objPart=self.browse(cr, uid, existingID, context=context)
                if (self.getUpdTime(objPart)<datetime.strptime(part['lastupdate'],'%Y-%m-%d %H:%M:%S')):
                    if self._iswritable(cr,uid,objPart):
                        del(part['lastupdate'])
                        if not self.write(cr,uid,[existingID], part , context=context, check=True):
                            raise osv.except_osv(_('Update Part Error'), _("Part %s cannot be updated" %(str(part['engineering_code']))))
                        hasSaved=True
                part['name']=objPart.name
            part['componentID']=existingID
            part['hasSaved']=hasSaved
            retValues.append(part)
            listedParts.append(part['engineering_code'])
        return retValues 

    def QueryLast(self, cr, uid, request=([],[]), default=None, context=None):
        """
            Query to return values based on columns selected.
        """
        objId=False
        expData=[]
        queryFilter, columns = request        
        if len(columns)<1:
            return expData
        if 'engineering_revision' in queryFilter:
            del queryFilter['engineering_revision']
        allIDs=self.search(cr,uid,queryFilter,order='engineering_revision',context=context)
        if len(allIDs)>0:
            objId=allIDs[0]
        if objId:
            tmpData=self.export_data(cr, uid, [objId], columns)
            if 'datas' in tmpData:
                expData=tmpData['datas']
        return expData

##  Menu action Methods
    def action_create_normalBom(self, cr, uid, ids, context=None):
        """
            Create a new Spare Bom if doesn't exist (action callable from views)
        """
        if not 'active_id' in context:
            return False
        return self.action_create_normalBom_WF(cr, uid, context['active_ids'])

    def _create_normalBom(self, cr, uid, idd, context=None):
        """
            Create a new Normal Bom (recursive on all EBom children)
        """
        defaults={}
        if idd in self.processedIds:
            return False
        checkObj=self.browse(cr, uid, idd, context)
        if not checkObj:
            return False
        bomType=self.pool.get('mrp.bom')
        if checkObj.engineering_revision:
            objBoms=bomType.search(cr, uid, [('name','=',checkObj.name),('engineering_revision','=',checkObj.engineering_revision),('type','=','normal'),('bom_id','=',False)])
            idBoms=bomType.search(cr, uid, [('name','=',checkObj.name),('engineering_revision','=',checkObj.engineering_revision),('type','=','ebom'),('bom_id','=',False)])
        else:
            objBoms=bomType.search(cr, uid, [('name','=',checkObj.name),('type','=','normal'),('bom_id','=',False)])
            idBoms=bomType.search(cr, uid, [('name','=',checkObj.name),('type','=','ebom'),('bom_id','=',False)])

        if not objBoms:
            if idBoms:
                self.processedIds.append(idd)
                newidBom=bomType.copy(cr, uid, idBoms[0], defaults, context)
                if newidBom:
                    bomType.write(cr,uid,[newidBom],{'name':checkObj.name,'product_id':checkObj.id,'type':'normal',},context=None)
                    oidBom=bomType.browse(cr,uid,newidBom,context=context)
                    ok_rows=self._summarizeBom(cr, uid, oidBom.bom_lines)
                    for bom_line in list(set(oidBom.bom_lines) ^ set(ok_rows)):
                        bomType.unlink(cr,uid,[bom_line.id],context=None)
                    for bom_line in ok_rows:
                        bomType.write(cr,uid,[bom_line.id],{'type':'normal','source_id':False,'name':bom_line.product_id.name,'product_qty':bom_line.product_qty,},context=None)
                        self._create_normalBom(cr, uid, bom_line.product_id.id, context)
        else:
            for bom_line in bomType.browse(cr,uid,objBoms[0],context=context).bom_lines:
                self._create_normalBom(cr, uid, bom_line.product_id.id, context)
        return False

    def _summarizeBom(self, cr, uid, datarows):
        dic={}
        for datarow in datarows:
            key=str(datarow.product_id.name)
            if key in dic:
                dic[key].product_qty=float(dic[key].product_qty)+float(datarow.product_qty)
            else:
                dic[key]=datarow
        retd=dic.values()
        return retd

##  Work Flow Internal Methods
    def _get_recursive_parts(self, cr, uid, ids, excludeStatuses, includeStatuses):
        """
            release the object recursively
        """
        stopFlag=False
        tobeReleasedIDs=ids
        children=[]
        for oic in self.browse(cr, uid, ids, context=None):
            children=self.browse(cr, uid, self._getChildrenBom(cr, uid, oic, 1), context=None)
            for child in children:
                if (not child.state in excludeStatuses) and (not child.state in includeStatuses):
                    stopFlag=True
                    break
                if child.state in includeStatuses:
                    if not child.id in tobeReleasedIDs:
                        tobeReleasedIDs.append(child.id)
        return (stopFlag,list(set(tobeReleasedIDs)))
    
    def action_create_normalBom_WF(self, cr, uid, ids, context=None):
        """
            Create a new Nornmal Bom if doesn't exist (action callable from code)
        """
        
        for idd in ids:
            self.processedIds=[]
            self._create_normalBom(cr, uid, idd, context)
        return False

    def _action_ondocuments(self,cr,uid,ids,action_name,context=None):
        """
            move workflow on documents having the same state of component 
        """
        docIDs=[]
        documentType=self.pool.get('ir.attachment')
        for oldObject in self.browse(cr, uid, ids, context=context):
            if (action_name!='transmit') and (action_name!='reject') and (action_name!='release'):
                check_state=oldObject.state
            else:
                check_state='confirmed'
            for document in oldObject.linkeddocuments:
                if document.state == check_state:
                    if not document.id in docIDs:
                        docIDs.append(document.id)
        if len(docIDs)>0:
            if action_name=='confirm':
                documentType.action_confirm(cr,uid,docIDs)
            elif action_name=='transmit':
                documentType.action_confirm(cr,uid,docIDs)
            elif action_name=='draft':
                documentType.action_draft(cr,uid,docIDs)
            elif action_name=='correct':
                documentType.action_draft(cr,uid,docIDs)
            elif action_name=='reject':
                documentType.action_draft(cr,uid,docIDs)
            elif action_name=='release':
                documentType.action_release(cr,uid,docIDs)
            elif action_name=='undermodify':
                documentType.action_cancel(cr,uid,docIDs)
            elif action_name=='suspend':
                documentType.action_suspend(cr,uid,docIDs)
            elif action_name=='reactivate':
                documentType.action_reactivate(cr,uid,docIDs)
            elif action_name=='obsolete':
                documentType.action_obsolete(cr,uid,docIDs)
        return docIDs

    def _iswritable(self, cr, user, oid):
        checkState=('draft')
        if not oid.engineering_writable:
            logging.warning("_iswritable : Part (%r - %d) is not writable." %(oid.engineering_code,oid.engineering_revision))
            return False
        if not oid.state in checkState:
            logging.warning("_iswritable : Part (%r - %d) is in status %r." %(oid.engineering_code,oid.engineering_revision,oid.state))
            return False
        if oid.engineering_code == False:
            logging.warning("_iswritable : Part (%r - %d) is without Engineering P/N." %(oid.name,oid.engineering_revision))
            return False
        return True  

    def action_draft(self,cr,uid,ids,context=None):
        """
            release the object
        """
        defaults={}
        defaults['engineering_writable']=True
        defaults['state']='draft'
        excludeStatuses=['draft','released','undermodify','obsoleted']
        includeStatuses=['confirmed','transmitted']
        stopFlag,allIDs=self._get_recursive_parts(cr, uid, ids, excludeStatuses, includeStatuses)
        self._action_ondocuments(cr,uid,allIDs,'draft')
        return self.write(cr, uid, allIDs, defaults, context=context, check=False)

    def action_confirm(self,cr,uid,ids,context=None):
        """
            action to be executed for Draft state
        """
        defaults={}
        defaults['engineering_writable']=False
        defaults['state']='confirmed'
        excludeStatuses=['confirmed','transmitted','released','undermodify','obsoleted']
        includeStatuses=['draft']
        stopFlag,allIDs=self._get_recursive_parts(cr, uid, ids, excludeStatuses, includeStatuses)
        self._action_ondocuments(cr,uid,allIDs,'confirm')
        return self.write(cr, uid, allIDs, defaults, context=context, check=False)

    def action_release(self,cr,uid,ids,context=None):
        """
           action to be executed for Released state
        """
        defaults={}
        excludeStatuses=['released','undermodify','obsoleted']
        includeStatuses=['confirmed']
        stopFlag,allIDs=self._get_recursive_parts(cr, uid, ids, excludeStatuses, includeStatuses)
        if len(allIDs)<1 or stopFlag:
            raise osv.except_osv(_('WorkFlow Error'), _("Part cannot be released."))
        for oldObject in self.browse(cr, uid, allIDs, context=context):
            last_id=self._getbyrevision(cr, uid, oldObject.engineering_code, oldObject.engineering_revision-1)
            if last_id != None:
                defaults['engineering_writable']=False
                defaults['state']='obsoleted'
                self.write(cr,uid,[last_id],defaults ,context=context,check=False)
            defaults['engineering_writable']=False
            defaults['state']='released'
        self._action_ondocuments(cr,uid,allIDs,'release')
        return self.write(cr,uid,allIDs,defaults ,context=context,check=False)

    def action_obsolete(self,cr,uid,ids,context=None):
        """
            obsolete the object
        """
        defaults={}
        defaults['engineering_writable']=False
        defaults['state']='obsoleted'
        excludeStatuses=['draft','confirmed','transmitted','undermodify','obsoleted']
        includeStatuses=['released']
        stopFlag,allIDs=self._get_recursive_parts(cr, uid, ids, excludeStatuses, includeStatuses)
        self._action_ondocuments(cr,uid,allIDs,'obsolete')
        return self.write(cr, uid, allIDs, defaults, context=context, check=False)

    def action_reactivate(self,cr,uid,ids,context=None):
        """
            reactivate the object
        """
        defaults={}
        defaults['engineering_writable']=True
        defaults['state']='released'
        excludeStatuses=['draft','confirmed','transmitted','released','undermodify','obsoleted']
        includeStatuses=['obsoleted']
        stopFlag,allIDs=self._get_recursive_parts(cr, uid, ids, excludeStatuses, includeStatuses)
        self._action_ondocuments(cr,uid,allIDs,'reactivate')
        return self.write(cr, uid, allIDs, defaults, context=context, check=False)

#   Overridden methods for this entity
    def create(self, cr, uid, vals, context=None):
        if not vals:
            return False
        existingIDs=self.search(cr, uid, [('name','=',vals['name'])], order = 'engineering_revision', context=context)
        if 'engineering_code' in vals:
            if vals['engineering_code'] == False:
                vals['engineering_code'] = vals['name']
        else:
            vals['engineering_code'] = vals['name']

        if ('name' in vals) and existingIDs:
            existingID=existingIDs[len(existingIDs)-1]
            if ('engineering_revision' in vals):
                existObj=self.browse(cr,uid,existingID,context=context)
                if existObj:
                    if vals['engineering_revision'] > existObj.engineering_revision:
                        vals['name']=existObj.name
                    else:
                        return existingID
            else:
                return existingID
            
        try:
            return super(plm_component,self).create(cr, uid, vals, context=context)
        except:
            raise osv.except_osv(_('Create Entity Error'), _("It has tried to create %r , %r"%(vals['name'],vals)))
            return False
         
    def write(self, cr, uid, ids, vals, context=None, check=True):
#         checkState=('confirmed','released','undermodify','obsoleted')
#         if check:
#             for customObject in self.browse(cr, uid, ids, context=context):
#                 if not customObject.engineering_writable:
#                     raise osv.except_osv(_('Edit Entity Error'), _("No changes are allowed on entity (%s)." %(customObject.name)))
#                     return False
#                 if customObject.state in checkState:
#                     raise osv.except_osv(_('Edit Entity Error'), _("The active state does not allow you to make save action on entity (%s)." %(customObject.name)))
#                     return False
#                 if customObject.engineering_code == False:
#                     vals['engineering_code'] = customObject.name
#                     # Force copy engineering_code to name if void
        return super(plm_component,self).write(cr, uid, ids, vals, context=context)  

    def copy(self,cr,uid,oid,defaults={},context=None):
        """
            Overwrite the default copy method
        """
        previous_name=self.browse(cr,uid,oid,context=context).name
        if not 'name' in defaults:
            new_name='Copy of %s'%previous_name
            l=self.search(cr,uid,[('name','like',new_name)],context=context)
            if len(l)>0:
                new_name='%s (%s)'%(new_name,len(l)+1)
            defaults['name']=new_name
            defaults['engineering_code']=new_name
            defaults['engineering_revision']=0
        #assign default value
        defaults['state']='draft'
        defaults['engineering_writable']=True
        defaults['write_date']=None
        defaults['linkeddocuments']=[]
        return super(plm_component,self).copy(cr,uid,oid,defaults,context=context)

    def unlink(self, cr, uid, ids, context=None):
        values={'state':'released',}
        checkState=('undermodify','obsoleted')
        for checkObj in self.browse(cr, uid, ids, context=context):
            existingID = self.search(cr, uid, [('engineering_code', '=', checkObj.engineering_code),('engineering_revision', '=', checkObj.engineering_revision-1)])
            if len(existingID)>0:
                oldObject=self.browse(cr, uid, existingID[0], context=context)
                if oldObject.state in checkState:
                    if not self.write(cr, uid, [oldObject.id], values, context, check=False):
                        logging.warning("unlink : Unable to update state to old component (%r - %d)." %(oldObject.engineering_code,oldObject.engineering_revision))
                        return False
        return super(plm_component,self).unlink(cr, uid, ids, context=context)

#   Overridden methods for this entity

plm_component()
