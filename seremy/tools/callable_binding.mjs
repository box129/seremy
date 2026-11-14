// Bounded lexical callable values. No callback-argument propagation or object dispatch.
import * as ts from 'typescript';
import {resolve} from 'node:path';
import {createHash} from 'node:crypto';

export const CALLABLE_METHOD='typescript-callable-checker-v0.1';
export function unwrap(node){
  while(node&&(ts.isParenthesizedExpression(node)||ts.isAsExpression(node)||ts.isTypeAssertionExpression(node)||ts.isNonNullExpression(node)||ts.isSatisfiesExpression(node)))node=node.expression;
  return node;
}
export function callableDeclaration(node){
  if(!node||!ts.isVariableDeclaration(node)||!ts.isIdentifier(node.name)||!ts.isVariableDeclarationList(node.parent)||!(node.parent.flags&ts.NodeFlags.Const))return null;
  const fn=unwrap(node.initializer);
  if(!fn||!(ts.isArrowFunction(fn)||ts.isFunctionExpression(fn)))return null;
  return {declaration:node,nameNode:node.name,fn,kind:'callable_declaration'};
}
function containingCallable(fn){
  let parent=fn.parent;
  while(parent&&(ts.isParenthesizedExpression(parent)||ts.isAsExpression(parent)||ts.isTypeAssertionExpression(parent)||ts.isNonNullExpression(parent)||ts.isSatisfiesExpression(parent)))parent=parent.parent;
  const info=callableDeclaration(parent);
  return info?.fn===fn?info:null;
}
function functionIdentity(node){
  const constant=containingCallable(node);
  if(constant)return constant;
  if(ts.isFunctionExpression(node)&&node.name)return {declaration:node,nameNode:node.name,fn:node,kind:'function_expression'};
  if(ts.isMethodDeclaration(node)&&ts.isIdentifier(node.name))return {declaration:node,nameNode:node.name,fn:node,kind:'method_declaration'};
  return null;
}
export function lexicalCallableDeclaration(node){
  const constant=callableDeclaration(node);
  if(constant)return constant;
  // A const function expression already has its variable identity; don't duplicate it.
  if(ts.isFunctionExpression(node)&&!containingCallable(node))return functionIdentity(node);
  return ts.isMethodDeclaration(node)?functionIdentity(node):null;
}

export function createCallableBinder({checker,inputs,program,context,options,syntaxDiagnostics,writtenSymbols}){
  const unsafeFiles=new Set();
  const inspect=node=>{
    if(ts.isWithStatement(node)||(ts.isCallExpression(node)&&ts.isIdentifier(node.expression)&&node.expression.text==='eval'))unsafeFiles.add(node.getSourceFile().fileName);
    ts.forEachChild(node,inspect);
  };
  for(const path of inputs.keys()){const source=program.getSourceFile(path);if(source)inspect(source);}
  const failure=reason=>({outcome:'UNSUPPORTED',reason,context});
  const importNode=symbol=>{
    let node=symbol?.declarations?.find(d=>ts.isImportClause(d)||ts.isImportSpecifier(d)||ts.isNamespaceImport(d));
    while(node&&!ts.isImportDeclaration(node))node=node.parent;
    return node;
  };
  function unavailable(imported){
    const path=imported?.moduleSpecifier?.text;
    const mapped=Object.keys(options.paths||{}).some(pattern=>{
      const [prefix,suffix]=pattern.split('*');return suffix===undefined?path===pattern:path?.startsWith(prefix)&&path.endsWith(suffix);
    });
    return path&&!path.startsWith('.')&&!mapped?{outcome:'EXTERNAL',reason:'bare_specifier',target:path,context}:
      {outcome:'MISSING',reason:imported?'unresolved_import':'no_binding_within_profile',context};
  }
  function expressionSymbol(expression){
    expression=unwrap(expression);
    if(ts.isIdentifier(expression))return {symbol:checker.getSymbolAtLocation(expression)};
    if(!ts.isPropertyAccessExpression(expression)||expression.questionDotToken||!ts.isIdentifier(expression.expression))return {error:failure('receiver_not_immutable_namespace')};
    const receiver=checker.getSymbolAtLocation(expression.expression);
    const declaration=receiver?.declarations?.find(ts.isNamespaceImport);
    if(!declaration)return {error:failure('receiver_not_immutable_namespace')};
    if(declaration.parent.isTypeOnly)return {error:failure('type_only_alias_has_no_runtime_value')};
    return {symbol:checker.getSymbolAtLocation(expression.name),imported:importNode(receiver)};
  }
  function target(symbol,seen=new Set(),imported=null){
    if(seen.size>=128)return {error:failure('alias_depth_limit')};
    imported=importNode(symbol)||imported;
    while(symbol&&(symbol.flags&ts.SymbolFlags.Alias)){
      if(seen.size>=128)return {error:failure('alias_depth_limit')};
      if(seen.has(symbol))return {error:failure('alias_cycle')};seen.add(symbol);
      if(symbol.declarations?.some(d=>ts.isTypeOnlyImportOrExportDeclaration(d)))return {error:failure('type_only_alias_has_no_runtime_value')};
      symbol=checker.getImmediateAliasedSymbol(symbol);
    }
    if(!symbol)return {error:unavailable(imported)};
    if(seen.has(symbol))return {error:failure('alias_cycle')};seen.add(symbol);
    if(writtenSymbols.has(symbol))return {error:failure('binding_reassigned_in_snapshot')};
    const declarations=(symbol.declarations||[]).filter(d=>!(ts.isIdentifier(d)&&
      (ts.isPropertyAccessExpression(d.parent)||ts.isElementAccessExpression(d.parent))&&d.parent.expression===d));
    if(!declarations.length)return {error:unavailable(imported)};
    if(declarations.every(ts.isFunctionDeclaration)){
      const bodies=declarations.filter(d=>d.body);
      if(bodies.length>1)return {error:{outcome:'AMBIGUOUS',reason:'multiple_implementations',context}};
      if(!bodies.length)return {error:failure('declaration_only_target')};
      const declaration=bodies[0];
      return declaration.name?{declaration,nameNode:declaration.name,kind:'function_declaration'}:{error:failure('anonymous_function_identity_not_supported')};
    }
    if(declarations.length!==1)return {error:failure('callable_value_target_not_established')};
    const declaration=declarations[0];
    if(ts.isFunctionExpression(declaration))return functionIdentity(declaration)||{error:failure('callable_value_target_not_established')};
    const callable=callableDeclaration(declaration);
    if(callable)return callable;
    if(!ts.isVariableDeclaration(declaration)||!ts.isIdentifier(declaration.name)||!ts.isVariableDeclarationList(declaration.parent)||!(declaration.parent.flags&ts.NodeFlags.Const))return {error:failure('mutable_or_dynamic_callable_target')};
    const initializer=unwrap(declaration.initializer);
    if(!initializer||!(ts.isIdentifier(initializer)||ts.isPropertyAccessExpression(initializer)))return {error:failure('callable_value_target_not_established')};
    const next=expressionSymbol(initializer);
    return next.error?next:target(next.symbol,seen,next.imported||imported);
  }
  return function bindCallable(source,call,mapRange){
    if(syntaxDiagnostics(source).length)return failure('syntax_diagnostics');
    if(unsafeFiles.has(source.fileName))return failure('dynamic_scope_in_source');
    let fileOwner=false;
    for(let parent=call.parent;parent&&!ts.isSourceFile(parent);parent=parent.parent){
      if(ts.isClassDeclaration(parent)||ts.isClassExpression(parent)){fileOwner=true;break;}
      if(ts.isFunctionLike(parent)){
        if(!(ts.isFunctionDeclaration(parent)&&parent.name)&&!functionIdentity(parent))fileOwner=true;
        break;
      }
    }
    if(call.questionDotToken||call.expression.questionDotToken)return failure('optional_call_outside_profile');
    const initial=expressionSymbol(call.expression);
    if(initial.error)return initial.error;
    const found=target(initial.symbol,new Set(),initial.imported);
    if(found.error)return found.error;
    const targetSource=found.declaration.getSourceFile(),input=inputs.get(resolve(targetSource.fileName));
    if(!input||syntaxDiagnostics(targetSource).length)return failure('target_outside_valid_snapshot');
    if(unsafeFiles.has(targetSource.fileName))return failure('dynamic_scope_in_target');
    return {outcome:'RESOLVED_SINGLE',context,...(fileOwner?{
      source_owner:'file:'+inputs.get(resolve(source.fileName)).id,
      source_owner_reason:'lexical_callable_owner_not_identified'
    }:{}),target:{file_id:input.id,
      content_sha256:createHash('sha256').update(input.raw).digest('hex'),kind:found.kind,name:found.nameNode.text,
      name_byte:mapRange(targetSource.text,[found.nameNode.getStart(targetSource),found.nameNode.end])}};
  };
}
