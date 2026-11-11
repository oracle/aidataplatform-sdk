# Copyright (c) 2026, Oracle and/or its affiliates.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/
from __future__ import annotations

import contextlib
import http.client
from http.server import BaseHTTPRequestHandler, HTTPServer
import importlib.util
import io
import errno
import os
import struct
import json
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'codex/skills/aidp-cli/scripts/folder-transfer.py'
spec = importlib.util.spec_from_file_location('folder_transfer', SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
PAR = 'https://storage.example/p/SECRET-PAR-TOKEN/o/archive.zip'

class FolderTransferTests(unittest.TestCase):
    def arguments(self, action, target, source, destination):
        return [action, '--aidpOCID', 'instance', '--'+target+'Key', 'target',
                '--sourcePath', str(source), '--destPath', str(destination),
                '--profile', 'chosen', '--endpoint', 'https://aidp.example']

    def archive(self, path):
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('file.txt', 'contents')

    def test_upload_both_targets_and_completion_metadata(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp)/'MyFolder.zip'; self.archive(source)
            for target in ['workspace', 'volume']:
                with self.subTest(target=target):
                    out = io.StringIO()
                    with patch.object(module, 'api', side_effect=[{'operationKey':'job-1','uploadUrl':PAR}, {}]) as api, patch.object(module, 'put_archive', return_value=('etag-secret', source.stat().st_size)) as upload, patch.object(module, 'wait') as wait, contextlib.redirect_stdout(out):
                        self.assertEqual(module.main(self.arguments('upload',target,source,'.')),0)
                    self.assertNotIn(PAR,out.getvalue());self.assertNotIn('etag-secret',out.getvalue())
                    self.assertEqual(api.call_args_list[0].args[2]['isOverwrite'],False)
                    self.assertEqual(api.call_args_list[1].args[2]['operationKey'],'job-1')
                    self.assertEqual(api.call_args_list[1].args[2]['sizeInBytes'],source.stat().st_size)
                    self.assertEqual(upload.call_args.args[0],PAR)
                    wait.assert_called_once()

    def test_folder_source_packages_contents_and_cleans_temporary_archive(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)/'MyFolder';folder.mkdir()
            (folder/'.hidden').write_text('hidden')
            (folder/'file.txt').write_text('data')
            (folder/'empty').mkdir()
            for target in ['workspace','volume']:
                captured=[]
                args=self.arguments('upload',target,folder,'.')
                args[args.index('--sourcePath')]='--sourceFolderPath'
                def upload(url,archive,timeout):
                    captured.append(archive)
                    with zipfile.ZipFile(archive) as contents:
                        self.assertEqual(set(contents.namelist()),{'.hidden','file.txt','empty/'})
                    return 'etag',archive.stat().st_size
                with patch.object(module,'api',side_effect=[{'operationKey':'job-folder','uploadUrl':PAR},{}]), patch.object(module,'put_archive',side_effect=upload), patch.object(module,'wait'), contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(module.main(args),0)
                self.assertFalse(captured[0].exists())
                self.assertTrue((folder/'.hidden').exists())

    def test_folder_source_cleanup_on_failed_upload_and_no_retry(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)/'MyFolder';folder.mkdir();(folder/'file').write_text('data')
            captured=[]
            args=self.arguments('upload','workspace',folder,'.')
            args[args.index('--sourcePath')]='--sourceFolderPath'
            def fail(url,archive,timeout):
                captured.append(archive)
                raise RuntimeError(PAR)
            out=io.StringIO()
            with patch.object(module,'api',return_value={'operationKey':'job-failed','uploadUrl':PAR}) as api, patch.object(module,'put_archive',side_effect=fail), contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
                self.assertEqual(module.main(args),1)
            self.assertEqual(api.call_count,1)
            self.assertFalse(captured[0].exists())
            self.assertNotIn(PAR,out.getvalue())

    def test_explicit_archive_source_and_folder_symlink_rejection(self):
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/'MyFolder.zip';self.archive(source)
            args=self.arguments('upload','workspace',source,'.')
            args[args.index('--sourcePath')]='--sourceZipPath'
            with patch.object(module,'api',side_effect=[{'operationKey':'job-archive','uploadUrl':PAR},{}]), patch.object(module,'put_archive',return_value=('etag',source.stat().st_size)),patch.object(module,'wait'),contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(module.main(args),0)
            folder=Path(temp)/'folder';folder.mkdir();(folder/'link').symlink_to(source)
            args=self.arguments('upload','workspace',folder,'.')
            args[args.index('--sourcePath')]='--sourceFolderPath'
            with patch.object(module,'api') as api,contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(module.main(args),1)
                api.assert_not_called()

    def test_download_both_targets_waits_before_get(self):
        with tempfile.TemporaryDirectory() as temp:
            for target in ['workspace','volume']:
                events=[];out=io.StringIO()
                with patch.object(module,'api',return_value={'operationKey':'job-2','downloadUrl':PAR}), patch.object(module,'wait',side_effect=lambda *a:events.append('wait')), patch.object(module,'get_archive',side_effect=lambda url,path,timeout:events.append(('get',path.name))), contextlib.redirect_stdout(out):
                    self.assertEqual(module.main(self.arguments('download',target,'imports/MyFolder',temp)),0)
                self.assertEqual(events[0],'wait');self.assertRegex(events[1][1],r'^MyFolder-\d{14}\.zip$')
                self.assertNotIn(PAR,out.getvalue())

    def test_format_restriction_and_collision_precede_remote_call(self):
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/'bundle.aidp';source.write_bytes(b'archive')
            with patch.object(module,'api') as api, contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(module.main(self.arguments('upload','volume',source,'.')),1)
                api.assert_not_called()
            existing=Path(temp)/'MyFolder-20261012120000.zip';existing.write_bytes(b'existing')
            with patch.object(module,'api') as api, contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(module.main(self.arguments('download','workspace','MyFolder',existing)),1)
                api.assert_not_called()
            self.assertEqual(existing.read_bytes(),b'existing')

    def test_sensitive_exceptions_and_cli_errors_are_suppressed(self):
        args=module.parser().parse_args(self.arguments('download','workspace','folder','/tmp'))
        result=SimpleNamespace(returncode=1,stdout='Response:\n'+json.dumps({'status':400,'message':PAR}),stderr=PAR)
        with patch.object(module.subprocess,'run',return_value=result):
            with self.assertRaises(module.TransferError) as error:module.api(args,['test'])
            self.assertNotIn(PAR,str(error.exception))
        out=io.StringIO()
        with patch.object(module,'transfer',side_effect=RuntimeError(PAR)),contextlib.redirect_stderr(out):
            self.assertEqual(module.main(self.arguments('download','workspace','folder','/tmp')),1)
        self.assertNotIn(PAR,out.getvalue());self.assertNotIn('SECRET-PAR-TOKEN',out.getvalue())

    def test_failure_and_timeout_do_not_repeat_creation(self):
        args=module.parser().parse_args(self.arguments('download','workspace','folder','/tmp'))
        with patch.object(module,'api',return_value={'status':'FAILED'}) as api:
            with self.assertRaises(module.TransferError):module.wait(args,'job-1')
            self.assertEqual(api.call_count,1)
        with patch.object(module.time,'monotonic',side_effect=[0,2000]),patch.object(module,'api') as api:
            with self.assertRaises(module.TransferError):module.wait(args,'job-1')
            api.assert_not_called()

    def test_tls_context_keeps_verification_and_loads_available_ca_bundle(self):
        import certifi
        with patch.object(module.ssl,'create_default_context') as create:
            context=module.tls_context()
            context.load_verify_locations.assert_called_once_with(cafile=certifi.where())
            self.assertIs(context,create.return_value)

    def test_cli_json_error_on_stderr_stays_private(self):
        args=module.parser().parse_args(self.arguments('download','workspace','folder','/tmp'))
        result=SimpleNamespace(returncode=1,stdout='',stderr=json.dumps({'status':400,'code':'InvalidParameter','message':PAR}))
        with patch.object(module.subprocess,'run',return_value=result):
            with self.assertRaises(module.TransferError) as error:module.api(args,['test'])
        self.assertIn('HTTP 400',str(error.exception))
        self.assertNotIn(PAR,str(error.exception))

    def test_streamed_put_and_zip_download(self):
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/'source.zip';self.archive(source)
            class Response(io.BytesIO):
                status=200
                def getheader(self,name):
                    return 'etag-secret' if name=='ETag' else str(len(self.getvalue())) if name=='Content-Length' else None
            sent=[]
            def upload(url,method,timeout,data=None,headers=None):
                self.assertEqual(method,'PUT')
                sent.append(b''.join(data))
                self.assertEqual(headers['Content-Length'],str(len(sent[0])))
                return Response(b'')
            with patch.object(module,'par_request',side_effect=upload):
                etag,size=module.put_archive(PAR,source,120)
            self.assertEqual(sent[0],source.read_bytes());self.assertEqual(size,source.stat().st_size)
            destination=Path(temp)/'download.zip'
            with patch.object(module,'par_request',return_value=Response(source.read_bytes())):
                module.get_archive(PAR,destination,120)
            self.assertEqual(destination.read_bytes(),source.read_bytes())
            self.assertEqual(sorted(p.name for p in Path(temp).iterdir()),['download.zip','source.zip'])

    def test_real_http_stream_framing_with_local_test_server(self):
        stored={}
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_PUT(self):
                stored['transfer_encoding']=self.headers.get('Transfer-Encoding')
                stored['bytes']=self.rfile.read(int(self.headers['Content-Length']))
                self.send_response(200);self.send_header('ETag','local-etag')
                self.send_header('Content-Length','0');self.end_headers()
            def do_GET(self):
                self.send_response(200);self.send_header('Content-Length',str(len(stored['bytes'])))
                self.end_headers();self.wfile.write(stored['bytes'])
        server=HTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':0.05},daemon=True)
        thread.start()
        def local_transport(handler,request):
            # Test-only transport adapter: production HTTPS verification is unchanged.
            return handler.do_open(http.client.HTTPConnection,request)
        try:
            with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ,{'NO_PROXY':'127.0.0.1'},clear=True), patch.object(module.urllib.request.HTTPSHandler,'https_open',local_transport):
                source=Path(temp)/'source.zip';self.archive(source)
                url=f'https://127.0.0.1:{server.server_port}/p/local-test/o/archive.zip'
                etag,size=module.put_archive(url,source,5)
                self.assertEqual(etag,'local-etag');self.assertEqual(size,source.stat().st_size)
                self.assertIsNone(stored['transfer_encoding'])
                self.assertEqual(stored['bytes'],source.read_bytes())
                destination=Path(temp)/'download.zip'
                module.get_archive(url,destination,5)
                self.assertEqual(destination.read_bytes(),source.read_bytes())
        finally:
            server.shutdown();thread.join(timeout=5);server.server_close()

    def test_corrupt_zip_is_not_published(self):
        data=io.BytesIO()
        with zipfile.ZipFile(data,'w',zipfile.ZIP_STORED) as z:z.writestr('file',b'original')
        corrupt=bytearray(data.getvalue());name_len,extra_len=struct.unpack_from('<HH',corrupt,26)
        corrupt[30+name_len+extra_len]^=1
        self.assertTrue(zipfile.is_zipfile(io.BytesIO(corrupt)))
        class Response(io.BytesIO):
            status=200
            def getheader(self,name):return str(len(corrupt)) if name=='Content-Length' else None
        with tempfile.TemporaryDirectory() as temp:
            destination=Path(temp)/'bad.zip'
            with patch.object(module,'par_request',return_value=Response(corrupt)):
                with self.assertRaises(module.TransferError):module.get_archive(PAR,destination,120)
            self.assertFalse(destination.exists())
            self.assertEqual(list(Path(temp).iterdir()),[])

    def test_hardlink_fallback_preserves_bytes_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/'source.zip';self.archive(source)
            dest=Path(temp)/'dest.zip'
            with patch.object(module.os,'link',side_effect=OSError(errno.EOPNOTSUPP,'not supported')):
                module.publish_download(source,dest)
                self.assertEqual(source.read_bytes(),dest.read_bytes())
                dest.write_bytes(b'existing')
                with self.assertRaises(module.TransferError):module.publish_download(source,dest)
                self.assertEqual(dest.read_bytes(),b'existing')

    def test_failed_exclusive_copy_removes_partial_output(self):
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/'source.zip';source.write_bytes(b'archive')
            dest=Path(temp)/'dest.zip'
            def fail(stream,target,**kwargs):
                target.write(b'partial')
                raise OSError(errno.EIO,'disk error')
            with patch.object(module.os,'link',side_effect=OSError(errno.EOPNOTSUPP,'not supported')), patch.object(module.shutil,'copyfileobj',side_effect=fail):
                with self.assertRaises(OSError):module.publish_download(source,dest)
            self.assertFalse(dest.exists())

    def test_explicit_aidp_path_and_redacted_api_diagnostics(self):
        args=module.parser().parse_args(self.arguments('download','workspace','folder','/tmp')+['--aidp','/custom path/aidp'])
        result=SimpleNamespace(returncode=1,stdout='',stderr=json.dumps({'status':404,'code':'NotAuthorizedOrNotFound','message':'Missing object '+PAR,'opc-request-id':'request-123'}))
        with patch.object(module.subprocess,'run',return_value=result) as run:
            with self.assertRaises(module.TransferError) as error:module.api(args,['test'])
        self.assertEqual(run.call_args.args[0][0],'/custom path/aidp')
        self.assertIn('NotAuthorizedOrNotFound',str(error.exception))
        self.assertIn('request-123',str(error.exception))
        self.assertNotIn('SECRET-PAR-TOKEN',str(error.exception))
        with patch.object(module.subprocess,'run',side_effect=FileNotFoundError()):
            with self.assertRaisesRegex(module.TransferError,'--aidp'):module.api(args,['test'])

    def test_encoded_and_bare_par_urls_are_redacted(self):
        for value in [PAR,PAR.replace('/','\\/'),module.unquote(PAR).replace(':','%3A').replace('/','%2F'),'/p/SECRET-PAR-TOKEN/o/file.zip']:
            self.assertNotIn('SECRET-PAR-TOKEN',module.safe_detail(value))

    def test_http_failure_closes_response_and_hides_par(self):
        body=io.BytesIO(b'private response')
        error=module.urllib.error.HTTPError(PAR,403,'denied',{},body)
        with patch.object(module.urllib.request,'build_opener') as build:
            build.return_value.open.side_effect=error
            with self.assertRaises(module.TransferError) as raised:module.par_request(PAR,'GET',120)
        self.assertTrue(body.closed)
        self.assertIn('HTTP 403',str(raised.exception))
        self.assertNotIn('SECRET-PAR-TOKEN',str(raised.exception))

    def test_proxy_handler_honors_https_proxy_and_no_proxy(self):
        with patch.dict(os.environ,{'HTTPS_PROXY':'http://proxy.example:8080','NO_PROXY':'storage.example'},clear=True), patch.object(module.urllib.request,'build_opener') as build:
            module.par_request(PAR,'GET',120)
            handler=build.call_args.args[0]
            self.assertEqual(handler.proxies['https'],'http://proxy.example:8080')
            request=module.urllib.request.Request(PAR)
            with patch.object(request,'set_proxy') as set_proxy:
                handler.proxy_open(request,'http://proxy.example:8080','https')
                set_proxy.assert_not_called()
        with patch.dict(os.environ,{'HTTPS_PROXY':'http://proxy.example:8080','NO_PROXY':'other.example'},clear=True):
            handler=module.urllib.request.ProxyHandler()
            request=module.urllib.request.Request(PAR)
            with patch.object(request,'set_proxy') as set_proxy:
                handler.proxy_open(request,'http://proxy.example:8080','https')
                set_proxy.assert_called_once_with('proxy.example:8080','http')

if __name__ == '__main__':unittest.main()
