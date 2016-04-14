__author__ = 'Xinyue'

from cvxpy import *
import numpy as np
import cvxpy as cvx
from objective import convexify_obj
from objective import convexify_para_obj
from constraint import convexify_para_constr
from constraint import convexify_constr

def dccp(self, max_iter = 100, tau = 0.005, mu = 1.2, tau_max = 1e8, solver = None, ccp_times = 1):
    if is_dccp(self)==True:
        convex_prob = dccp_transform(self) # convexify problem
        result = None
        if self.objective.NAME == 'minimize':
            cost_value = float("inf")
        else:
            cost_value = -float("inf")
        for t in range(ccp_times):
            dccp_ini(self, random=(ccp_times>1)) # random initial value is mandatory if ccp_times>1
            result_temp = iter_dccp_para(self, convex_prob, max_iter, tau, mu ,tau_max, solver)
            if (self.objective.NAME == 'minimize' and result_temp[0]<cost_value) or (self.objective.NAME == 'maximize' and result_temp[0]>cost_value):
                if t==0 or len(result_temp)<3 or result[1]<1e-4: # first ccp; no slack; slack small enough
                    result = result_temp
                    cost_value = result_temp[0]
        return result
    else:
        print "not a dccp problem"

def dccp_ini(self, times = 3, random = 0):
    dom_constr = self.objective.args[0].domain
    for arg in self.constraints:
        for dom in arg.args[0].domain:
            dom_constr.append(dom)
        for dom in arg.args[1].domain:
            dom_constr.append(dom)
    var_store = []
    init_flag = []
    for var in self.variables():
        var_store.append(np.zeros((var._rows,var._cols)))
        init_flag.append(var.value is None)
    for t in range(times):
        ini_cost = 0
        var_ind = 0
        for var in self.variables():
            if init_flag[var_ind] or random:
                var.value = np.random.randn(var._rows,var._cols)*10
            ini_cost += pnorm(var-var.value,2)
            var_ind += 1
        ini_obj = Minimize(ini_cost)
        ini_prob = Problem(ini_obj,dom_constr)
        ini_prob.solve()
        var_ind = 0
        for var in self.variables():
            var_store[var_ind] = var_store[var_ind] + var.value/float(times)
            var_ind += 1
    var_ind = 0
    for var in self.variables():
        var.value = var_store[var_ind]
        var_ind += 1

def is_dccp(self):
    flag = True
    for constr in self.constraints + [self.objective]:
        for arg in constr.args:
            if arg.curvature == 'UNKNOWN':
                flag = False
                return flag
    return flag

def dccp_transform(self):
    # split non-affine equality constraints
    constr = []
    for arg in self.constraints:
        if arg.OP_NAME == "==" and not arg.is_dcp():
            sp = arg.split()
            constr.append(sp[0])
            constr.append(sp[1])
        else:
            constr.append(arg)
    self.constraints = constr

    constr_new = [] # new constraints
    parameters = []
    flag = []
    parameters_cost = []
    flag_cost = []
    # constraints
    var_slack = [] # slack
    for constr in self.constraints:
        if not constr.is_dcp():
            flag.append(1)
            rows, cols = constr.size
            var_slack.append(Variable(rows, cols))
            temp = convexify_para_constr(constr)
            newcon = temp[0]   # new constraint without slack variable
            right = newcon.args[1] + var_slack[-1]
            constr_new.append(newcon.args[0]<=right)
            constr_new.append(var_slack[-1]>=0)
            parameters.append(temp[1])
            for dom in temp[2]:# domain
                constr_new.append(dom)
        else:
            flag.append(0)
            constr_new.append(constr)
    # cost functions
    if not self.objective.is_dcp():
        flag_cost.append(1)
        temp = convexify_para_obj(self.objective)
        cost_new =  temp[0] # new cost function
        parameters_cost.append(temp[1])
        parameters_cost.append(temp[2])
        for dom in temp[3]: # domain constraints
            constr_new.append(dom)
    else:
        flag_cost.append(0)
        cost_new = self.objective.args[0]
    # objective
    tau = Parameter()
    parameters.append(tau)
    if self.objective.NAME == 'minimize':
        for var in var_slack:
            cost_new += np.ones((var._cols,var._rows))*var*tau
        obj_new = Minimize(cost_new)
    else:
        for var in var_slack:
            cost_new -= var*tau
        obj_new = Maximize(cost_new)
    # new problem
    prob_new = Problem(obj_new, constr_new)
    return prob_new, parameters, flag, parameters_cost, flag_cost, var_slack

def iter_dccp_para(self, convex_prob, max_iter, tau, mu, tau_max, solver):
    # keep the values from the initialization
    previous_cost = float("inf")
    variable_pres_value = []
    for var in self.variables():
        variable_pres_value.append(var.value)
    it = 1
    while it<=max_iter and all(var.value is not None for var in self.variables()):
        # cost functions
        if convex_prob[4][0] == 1:
            convex_prob[3][0].value = self.objective.args[0].value
            G = self.objective.args[0].gradient
            for key in G:
                # damping
                flag_G = np.any(np.isnan(G[key])) or np.any(np.isinf(G[key]))
                while flag_G:
                    var_index = self.variables().index(key)
                    key.value = 0*key.value + 1* variable_pres_value[var_index]
                    G = self.objective.args[0].gradient
                    flag_G = np.any(np.isnan(G[key])) or np.any(np.isinf(G[key]))
                # gradient parameter
                for d in range(key.size[1]):
                    convex_prob[3][1][key][1][d].value = G[key][:,d,:,0]
                # var value parameter
                convex_prob[3][1][key][0].value = key.value
        #constraints
        count_constr = 0
        count_con_constr = 0
        for arg in self.constraints:
            if convex_prob[2][count_constr] == 1:
                for l in range(2):
                    if not len(convex_prob[1][count_con_constr][l]) == 0:
                        convex_prob[1][count_con_constr][l][0].value = arg.args[l].value
                        G = arg.args[l].gradient
                        for key in G:
                            # damping
                            flag_G = np.any(np.isnan(G[key])) or np.any(np.isinf(G[key]))
                            while flag_G:
                                var_index = self.variables().index(key)
                                key.value = 0.8*key.value + 0.2* variable_pres_value[var_index]
                                G = arg.args[l].gradient
                                flag_G = np.any(np.isnan(G[key])) or np.any(np.isinf(G[key]))
                            # gradient parameter
                            for d in range(key.size[1]):
                                convex_prob[1][count_con_constr][l][1][key][1][d].value = G[key][:,d,:,0]
                            # var value parameter
                            convex_prob[1][count_con_constr][l][1][key][0].value = key.value
                count_con_constr += 1
            count_constr += 1
        # keep the values from the previous iteration
        variable_pres_value = []
        for var in self.variables():
            variable_pres_value.append(var.value)
        # parameter tau
        convex_prob[1][-1].value = tau
        # solve the transformed problem
        if solver==None:
            print "iteration=",it, "cost value = ", convex_prob[0].solve(), "tau = ", tau
        else:
            print "iteration=",it, "cost value = ", convex_prob[0].solve(solver = solver), "tau = ", tau
        # print slack variables
        if not len(convex_prob[5])==0:
            max_slack = []
            for i in range(len(convex_prob[5])):
                max_slack.append(np.max(convex_prob[5][i].value))
            max_slack = np.max(max_slack)
            print "max slack = ", max_slack
        if np.abs(previous_cost - convex_prob[0].value) <= 1e-4: # terminate
            it = max_iter+1
        else:
            previous_cost = convex_prob[0].value
            tau = min([tau*mu,tau_max])
            it += 1
    var_value = []
    for var in self.variables():
        var_value.append(var.value)
    if not len(convex_prob[5])==0:
        return(self.objective.value, max_slack, var_value)
    else:
        return(self.objective.value, var_value)

def iter_dccp(self, max_iter, tau, miu, tau_max, solver):
    it = 1
    # keep the values from the previous iteration or initialization
    previous_cost = float("inf")
    variable_pres_value = []
    for var in self.variables():
        variable_pres_value.append(var.value)
    # each non-dcp constraint needs a slack variable
    var_slack = []
    for constr in self.constraints:
        if not constr.is_dcp():
            rows, cols = constr.size
            var_slack.append(Variable(rows, cols))

    while it<=max_iter and all(var.value is not None for var in self.variables()):
        constr_new = []
        #cost functions
        if not self.objective.is_dcp():
            ## temp = self.objective.convexify()
            temp = convexify_obj(self.objective)
            flag = temp[2]
            flag_var = temp[3]
            while flag == 1:
                #for var in flag_var:
                for var in self.variables:
                    var_index = self.variables().index(var)
                    var.value = 0.8*var.value + 0.2* variable_pres_value[var_index]
                temp = convexify_obj(self.objective)
                flag = temp[2]
                flag_var = temp[3]
            cost_new =  temp[0] # new cost function
            for dom in temp[1]: # domain constraints
                constr_new.append(dom)
        else:
            cost_new = self.objective.args[0]
        #constraints
        count_slack = 0
        for arg in self.constraints:
            if not arg.is_dcp():
                temp = convexify_constr(arg)
                flag = temp[2]
                flag_var = temp[3]
                while flag == 1:
                    #for var in flag_var:
                    for var in self.variables:
                        var_index = self.variables().index(var)
                        var.value = 0.8*var.value + 0.2* variable_pres_value[var_index]
                    temp = convexify_constr(arg)
                    flag = temp[2]
                    flag_var = temp[3]
                newcon = temp[0]   #new constraint without slack variable
                for dom in temp[1]:#domain
                    constr_new.append(dom)
                right = newcon.args[1] + var_slack[count_slack]
                constr_new.append(newcon.args[0]<=right)
                constr_new.append(var_slack[count_slack]>=0)
                count_slack = count_slack+1
            else:
                constr_new.append(arg)
        #objective
        if self.objective.NAME == 'minimize':
            for var in var_slack:
                cost_new += np.ones((var._cols,var._rows))*var*tau
            obj_new = Minimize(cost_new)
        else:
            for var in var_slack:
                cost_new -= var*tau
            obj_new = Maximize(cost_new)
        #new problem
        prob_new = Problem(obj_new, constr_new)
        variable_pres_value = []
        for var in self.variables():
            variable_pres_value.append(var.value)
        if not var_slack == []:
            if solver is None:
                print "iteration=",it, "cost value = ", prob_new.solve(), "tau = ", tau
            else:
                print "iteration=",it, "cost value = ", prob_new.solve(solver = solver), "tau = ", tau
            max_slack = []
            for i in range(len(var_slack)):
                max_slack.append(np.max(var_slack[i].value))
            max_slack = np.max(max_slack)
            print "max slack = ", max_slack
        else:
            if solver is None:
                co = prob_new.solve()
            else:
                co = prob_new.solve(solver = solver)
            print "iteration=",it, "cost value = ", co , "tau = ", tau
        if np.abs(previous_cost - prob_new.value) <= 1e-4: #terminate
            it_real = it
            it = max_iter+1
        else:
            previous_cost = prob_new.value
            it_real = it
            tau = min([tau*miu,tau_max])
            it += 1
    if not var_slack == []:
        return(it_real, tau, max(var_slack[i].value for i in range(len(var_slack))))
    else:
        return(it_real, tau)

cvx.Problem.register_solve("dccp", dccp)