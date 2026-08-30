use std::ffi::{c_uchar, c_ulong, c_void};
use std::path::{Path, PathBuf};

use anyhow::{anyhow, Context, Result};
use libloading::{Library, Symbol};

const FT_OK: c_ulong = 0;
const FT_TIMEOUT: c_ulong = 19;
const FT_OPEN_BY_INDEX: c_ulong = 0x0000_0010;

type FtHandle = *mut c_void;
type FtStatus = c_ulong;
type FtCreateFn = unsafe extern "C" fn(*mut c_void, c_ulong, *mut FtHandle) -> FtStatus;
type FtCloseFn = unsafe extern "C" fn(FtHandle) -> FtStatus;
type FtFlushPipeFn = unsafe extern "C" fn(FtHandle, c_uchar) -> FtStatus;
type FtSetStreamPipeFn =
    unsafe extern "C" fn(FtHandle, c_uchar, c_uchar, c_uchar, c_ulong) -> FtStatus;
type FtClearStreamPipeFn = unsafe extern "C" fn(FtHandle, c_uchar, c_uchar, c_uchar) -> FtStatus;
type FtReadPipeExFn = unsafe extern "C" fn(
    FtHandle,
    c_uchar,
    *mut c_void,
    c_ulong,
    *mut c_ulong,
    c_ulong,
) -> FtStatus;

struct Api {
    ft_create: FtCreateFn,
    ft_close: FtCloseFn,
    ft_flush_pipe: FtFlushPipeFn,
    ft_set_stream_pipe: FtSetStreamPipeFn,
    ft_clear_stream_pipe: FtClearStreamPipeFn,
    ft_read_pipe_ex: FtReadPipeExFn,
}

pub struct Device {
    _library: Library,
    api: Api,
    handle: FtHandle,
}

// The FT handle is process-local and only ever moved to a single owner thread.
// We do not share a Device concurrently across threads.
unsafe impl Send for Device {}

impl Device {
    pub fn open_default(
        library_path: Option<&Path>,
        pipe_id: u8,
        stream_size: u32,
    ) -> Result<Self> {
        let dylib = library_path
            .map(PathBuf::from)
            .unwrap_or_else(default_library_path);
        let library = unsafe { Library::new(&dylib) }
            .with_context(|| format!("failed to load {}", dylib.display()))?;
        let api = unsafe { load_api(&library)? };

        let mut handle: FtHandle = std::ptr::null_mut();
        let status =
            unsafe { (api.ft_create)(std::ptr::null_mut(), FT_OPEN_BY_INDEX, &mut handle) };
        ensure_status(status, "FT_Create")?;
        let mut device = Self {
            _library: library,
            api,
            handle,
        };
        if let Err(err) = device.configure_pipe(pipe_id, stream_size) {
            let _ = device.close();
            return Err(err);
        }
        Ok(device)
    }

    pub fn configure_pipe(&mut self, pipe_id: u8, stream_size: u32) -> Result<()> {
        let _ = unsafe {
            (self.api.ft_set_stream_pipe)(self.handle, 0, 0, pipe_id, stream_size as c_ulong)
        };
        let _ = unsafe { (self.api.ft_flush_pipe)(self.handle, pipe_id) };
        Ok(())
    }

    pub fn clear_stream_pipe(&mut self, pipe_id: u8) -> Result<()> {
        let status = unsafe { (self.api.ft_clear_stream_pipe)(self.handle, 0, 0, pipe_id) };
        ensure_status(status, "FT_ClearStreamPipe")
    }

    pub fn read_pipe(&mut self, pipe_id: u8, size: usize, timeout_ms: u32) -> Result<Vec<u8>> {
        let mut buffer = vec![0u8; size];
        let mut transferred: c_ulong = 0;
        let status = unsafe {
            (self.api.ft_read_pipe_ex)(
                self.handle,
                pipe_id,
                buffer.as_mut_ptr().cast(),
                size as c_ulong,
                &mut transferred,
                timeout_ms as c_ulong,
            )
        };
        if status != FT_OK && status != FT_TIMEOUT {
            ensure_status(status, "FT_ReadPipeEx")?;
        }
        buffer.truncate(transferred as usize);
        Ok(buffer)
    }

    pub fn close(&mut self) -> Result<()> {
        if self.handle.is_null() {
            return Ok(());
        }
        let status = unsafe { (self.api.ft_close)(self.handle) };
        self.handle = std::ptr::null_mut();
        ensure_status(status, "FT_Close")
    }
}

impl Drop for Device {
    fn drop(&mut self) {
        if !self.handle.is_null() {
            let _ = self.clear_stream_pipe(0x00);
            let _ = self.close();
        }
    }
}

unsafe fn load_api(library: &Library) -> Result<Api> {
    Ok(Api {
        ft_create: *load_symbol::<FtCreateFn>(library, b"FT_Create\0")?,
        ft_close: *load_symbol::<FtCloseFn>(library, b"FT_Close\0")?,
        ft_flush_pipe: *load_symbol::<FtFlushPipeFn>(library, b"FT_FlushPipe\0")?,
        ft_set_stream_pipe: *load_symbol::<FtSetStreamPipeFn>(library, b"FT_SetStreamPipe\0")?,
        ft_clear_stream_pipe: *load_symbol::<FtClearStreamPipeFn>(
            library,
            b"FT_ClearStreamPipe\0",
        )?,
        ft_read_pipe_ex: *load_symbol::<FtReadPipeExFn>(library, b"FT_ReadPipeEx\0")?,
    })
}

unsafe fn load_symbol<'a, T>(library: &'a Library, name: &[u8]) -> Result<Symbol<'a, T>> {
    library
        .get::<T>(name)
        .map_err(|err| anyhow!("missing symbol {}: {err}", String::from_utf8_lossy(name)))
}

fn ensure_status(status: FtStatus, op: &str) -> Result<()> {
    if status == FT_OK {
        Ok(())
    } else {
        Err(anyhow!("{op} failed with FT_STATUS={status}"))
    }
}

fn default_library_path() -> PathBuf {
    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    manifest_dir
        .ancestors()
        .nth(6)
        .map(|root| root.join("py").join("d3xx").join("libftd3xx.dylib"))
        .unwrap_or_else(|| PathBuf::from("py/d3xx/libftd3xx.dylib"))
}
