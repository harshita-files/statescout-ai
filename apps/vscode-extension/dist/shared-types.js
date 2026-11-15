/**
 * StateScout AI — shared API contract types.
 *
 * The single source of truth for the JSON that crosses the wire between the
 * FastAPI reporting backend (Track D) and the VS Code extension (Track A).
 * These mirror the Python dataclasses in `apps/agent/contracts.py`; when one
 * side changes, both change in the same PR.
 *
 * Types only — no runtime logic beyond the narrow helpers at the bottom.
 */

/** A role the crawler can browse as. Free-form: the policy author names them. */
                          

/** How a run ended. Mirrors the orchestrator's termination reasons. */
                               
                        
                 
                
             
            

/** Outcome of evaluating one policy clause against one observed state. */
                                           

/** Severity of a detected violation, as reported to the QA engineer. */
                                                              

/** Which set operation produced a violation (ADR-001 decision 6). */
                                                                 

/** Observation stability label from the Beta-Binomial confidence model (ADR-002). */
                                                                           

/** Origin of an audit rule (`user` typed or `generated` from site inspection). */
                                              

/** Rule verification category in the dynamic audit engine. */
                      
              
             
                 
             
          
              

/** A node in the exploration graph: one distinct UI state. */
                            
                                                                               
                  
              
                
             
                                                         
                
                                
                      
 

/** A directed edge: performing `actionId` in `fromStateId` led to `toStateId`. */
                            
                      
                    
                   
                                                             
                
                                                                          
                      
 

/** A policy clause the UI must not violate. */
                                  
                        
                                                                          
                                            
                                                          
                  
                                                              
                
                                                                           
                     
 

/** A detected policy violation, anchored to a state and an expectation. */
                            
                      
                  
                        
                                                                       
                          
                     
                                                   
                    
                                                                  
             
                            
                        
                                  
    
                     
 

/** Everything the extension needs to render one completed (or running) scan. */
                          
                
                    
             
                                                                     
                    
                            
                                              
           
                   
                  
                       
                           
    
 

/** `GET /runs/{runId}/graph` */
                                
                
                      
                     
 

/** `GET /runs/{runId}/report` */
                                 
               
                                  
                          
 

/** `POST /runs` */
                                  
                    
             
                                                    
                     
                      
 

/** Uniform error envelope for every non-2xx API response. */
                           
                
                        
 

// ---------------------------------------------------------------------------
// Dynamic Audit API contracts (`services/api/audits.py` & `audit_models.py`)
// ---------------------------------------------------------------------------

/** A plain-language or auto-generated audit rule (`apps/agent/audit_models.py::Rule`). */
                            
                  
               
                      
                      
                           
                                   
 

/** A finding emitted by the dynamic audit runner (`apps/agent/audit_models.py::Finding`). */
                               
                     
                         
                   
              
                     
                
                    
                                                                         
                     
                            
                     
                    
 

/** A page skipped due to safety policy (`robots`, `captcha`, `login_wall`, `rate_limit`). */
                              
              
                 
 

/** `GET /audits/{id}` — complete dynamic audit report. */
                              
                   
              
                                                   
                     
                           
                         
          
                                           
                                           
    
                                 
                       
 

/** `POST /audits` — start a dynamic audit run. */
                                    
              
                          
                                                                                     
                       
                      
                       
                       
                               
                           
                          
                        
 

/** True when the run has reached a state the UI should stop polling. */
export function isTerminal(run         )          {
  return run.status === "completed" || run.status === "failed";
}

/** True when a dynamic audit report has reached a terminal status. */
export function isAuditTerminal(report                             )          {
  return (
    report.status === "done" ||
    report.status === "error" ||
    report.status === "stopped"
  );
}

/** Violations worth interrupting the QA engineer for. */
export function isBlocking(violation           )          {
  return violation.severity === "high" || violation.severity === "critical";
}

/** Extract the Beta-Binomial observation label (`stable`, `flaky`, `insufficient_evidence`) from finding evidence. */
export function extractConfidenceLabel(
  finding                                               ,
)                  {
  for (const item of finding.evidence) {
    if (item.includes("observation: stable")) return "stable";
    if (item.includes("observation: flaky")) return "flaky";
    if (item.includes("observation: insufficient_evidence")) {
      return "insufficient_evidence";
    }
  }
  return finding.confidence >= 0.6 ? "stable" : "flaky";
}
