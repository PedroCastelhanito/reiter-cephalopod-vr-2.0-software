// T07/T08: minimal SDK ABI ownership shim. Scientific processing stays in Python.
// Build against NVIDIA Optical Flow SDK 2.x headers and the installed CUDA Toolkit.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <cuda.h>
#include <nvOpticalFlowCuda.h>
#if NV_OF_API_MAJOR_VERSION != 2 || NV_OF_API_MINOR_VERSION != 0
#error "This adapter requires Optical Flow SDK API 2.0 headers; do not silently change the ABI."
#endif
#include <cstdint>
#include <cstring>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
thread_local std::string error;
void cuda_check(CUresult code) {
    if (code != CUDA_SUCCESS) throw std::runtime_error("CUDA status " + std::to_string(code));
}
void of_check(NV_OF_STATUS code) {
    if (code != NV_OF_SUCCESS) throw std::runtime_error("NVOF status " + std::to_string(code));
}
struct Buffer {
    NvOFGPUBufferHandle handle{};
    CUdeviceptr pointer{};
    size_t pitch{};
};
struct Session {
    HMODULE library{};
    NV_OF_CUDA_API_FUNCTION_LIST api{};
    CUcontext context{};
    CUstream stream{};
    NvOFHandle flow{};
    Buffer inputs[2], output, cost;
    void *host_input{}, *host_output{}, *host_cost{};
    uint32_t width{}, height{}, columns{}, rows{};
    unsigned previous{};
    bool pending{}, has_baseline{}, pair{}, first_pair{true}, hints{};
    size_t allocation{}, maximum{};
    DWORD owner{GetCurrentThreadId()};
    void current() {
        if (GetCurrentThreadId() != owner) throw std::runtime_error("NVOF thread ownership violation");
        cuda_check(cuCtxSetCurrent(context));
    }
    void reserve(size_t size) {
        if (size > maximum-allocation) throw std::runtime_error("NVOF allocation budget exceeded");
        allocation += size;
    }
    void buffer(Buffer& result, uint32_t w, uint32_t h, NV_OF_BUFFER_USAGE usage, NV_OF_BUFFER_FORMAT format) {
        NV_OF_BUFFER_DESCRIPTOR desc{};
        desc.width=w; desc.height=h; desc.bufferUsage=usage; desc.bufferFormat=format;
        of_check(api.nvOFCreateGPUBufferCuda(flow,&desc,NV_OF_CUDA_BUFFER_TYPE_CUDEVICEPTR,&result.handle));
        {
            NV_OF_CUDA_BUFFER_STRIDE_INFO stride{};
            of_check(api.nvOFGPUBufferGetStrideInfo(result.handle,&stride));
            if(stride.numPlanes!=1) throw std::runtime_error("NVOF expected one buffer plane");
            result.pitch=stride.strideInfo[0].strideXInBytes;
            const size_t row=static_cast<size_t>(w)*(format==NV_OF_BUFFER_FORMAT_SHORT2?4:1);
            if(result.pitch<row) throw std::runtime_error("NVOF invalid native pitch");
            reserve(result.pitch*h);
            result.pointer=api.nvOFGPUBufferGetCUdeviceptr(result.handle);
            if(!result.pointer) throw std::runtime_error("NVOF missing CUDA device pointer");
        }
    }
    std::vector<uint32_t> caps(NV_OF_CAPS kind) {
        uint32_t count{};
        of_check(api.nvOFGetCaps(flow,kind,nullptr,&count));
        if(!count || count>64) throw std::runtime_error("NVOF invalid capability count");
        std::vector<uint32_t> result(count);
        of_check(api.nvOFGetCaps(flow,kind,result.data(),&count));
        if(count!=result.size()) throw std::runtime_error("NVOF capability count changed");
        return result;
    }
    void upload(unsigned slot, const void* data) {
        std::memcpy(host_input,data,static_cast<size_t>(width)*height);
        CUDA_MEMCPY2D copy{};
        copy.srcMemoryType=CU_MEMORYTYPE_HOST; copy.srcHost=host_input; copy.srcPitch=width;
        copy.dstMemoryType=CU_MEMORYTYPE_DEVICE; copy.dstDevice=inputs[slot].pointer; copy.dstPitch=inputs[slot].pitch;
        copy.WidthInBytes=width; copy.Height=height;
        pending=true; // Retain storage even if an enqueue reports failure.
        cuda_check(cuMemcpy2DAsync(&copy,stream));
    }
    void download(const Buffer& buffer, void* host, size_t row) {
        CUDA_MEMCPY2D copy{};
        copy.srcMemoryType=CU_MEMORYTYPE_DEVICE; copy.srcDevice=buffer.pointer; copy.srcPitch=buffer.pitch;
        copy.dstMemoryType=CU_MEMORYTYPE_HOST; copy.dstHost=host; copy.dstPitch=row;
        copy.WidthInBytes=row; copy.Height=rows;
        cuda_check(cuMemcpy2DAsync(&copy,stream));
    }
    bool complete() {
        current();
        auto status=cuStreamQuery(stream);
        if(status==CUDA_ERROR_NOT_READY) return false;
        cuda_check(status);
        if(pending) {
            if(pair) { previous=1-previous; first_pair=false; }
            has_baseline=true; pending=false; pair=false;
        }
        return true;
    }
    void destroy() {
        if(context) current();
        if(stream && !complete()) throw std::runtime_error("NVOF work still pending");
        for(auto* b:{&cost,&output,&inputs[1],&inputs[0]}) {
            if(b->handle) { of_check(api.nvOFDestroyGPUBufferCuda(b->handle)); b->handle=nullptr; }
        }
        if(flow) { of_check(api.nvOFDestroy(flow)); flow=nullptr; }
        for(auto* p:{&host_cost,&host_output,&host_input}) {
            if(*p) { cuda_check(cuMemFreeHost(*p)); *p=nullptr; }
        }
        if(stream) { cuda_check(cuStreamDestroy(stream)); stream=nullptr; }
        if(context) { cuda_check(cuCtxDestroy(context)); context=nullptr; }
        if(library) { FreeLibrary(library); library=nullptr; }
    }
};
}
#define EXPORT extern "C" __declspec(dllexport)
#define TRY try {
#define CATCH } catch(const std::exception& e) { error=e.what(); return -1; }
EXPORT const char* cephvr_nvof_error() { return error.c_str(); }
EXPORT int cephvr_nvof_create(int device, uint32_t width, uint32_t height, uint32_t grid,
                            int preset, int cost, int hints, uint64_t maximum, Session** result) {
    // Return the owner before creation so failed preparation can reconcile partial resources.
    *result=nullptr;
    TRY
    *result=new Session();
    auto& s=**result; s.width=width; s.height=height; s.maximum=maximum; s.hints=hints!=0;
    if(!width || !height || !(grid==1 || grid==2 || grid==4)) throw std::runtime_error("invalid input/grid dimensions");
    s.columns=(width+grid-1)/grid; s.rows=(height+grid-1)/grid;
    cuda_check(cuInit(0)); CUdevice dev{}; cuda_check(cuDeviceGet(&dev,device));
    cuda_check(cuCtxCreate_v2(&s.context,CU_CTX_SCHED_YIELD,dev));
    cuda_check(cuStreamCreate(&s.stream,CU_STREAM_NON_BLOCKING));
    s.library=LoadLibraryExW(L"nvofapi64.dll",nullptr,LOAD_LIBRARY_SEARCH_SYSTEM32);
    if(!s.library) throw std::runtime_error("NVIDIA OF driver library unavailable");
    using Create=NV_OF_STATUS (NVOFAPI*)(uint32_t,NV_OF_CUDA_API_FUNCTION_LIST*);
    auto create=reinterpret_cast<Create>(GetProcAddress(s.library,"NvOFAPICreateInstanceCuda"));
    if(!create) throw std::runtime_error("NVIDIA OF CUDA entry point unavailable");
    of_check(create(NV_OF_API_VERSION,&s.api));
    of_check(s.api.nvCreateOpticalFlowCuda(s.context,&s.flow));
    auto grids=s.caps(NV_OF_CAPS_SUPPORTED_OUTPUT_GRID_SIZES);
    bool supported=false; for(auto value:grids) supported|=value==grid;
    if(!supported || width<s.caps(NV_OF_CAPS_WIDTH_MIN)[0] || height<s.caps(NV_OF_CAPS_HEIGHT_MIN)[0]
       || width>s.caps(NV_OF_CAPS_WIDTH_MAX)[0] || height>s.caps(NV_OF_CAPS_HEIGHT_MAX)[0])
        throw std::runtime_error("requested source/grid unsupported by physical device");
    NV_OF_INIT_PARAMS init{}; init.width=width; init.height=height;
    init.outGridSize=static_cast<NV_OF_OUTPUT_VECTOR_GRID_SIZE>(grid);
    init.mode=NV_OF_MODE_OPTICALFLOW; init.perfLevel=static_cast<NV_OF_PERF_LEVEL>(preset);
    init.enableOutputCost=cost?NV_OF_TRUE:NV_OF_FALSE;
    of_check(s.api.nvOFInit(s.flow,&init));
    of_check(s.api.nvOFSetIOCudaStreams(s.flow,s.stream,s.stream));
    for(auto& input:s.inputs) s.buffer(input,width,height,NV_OF_BUFFER_USAGE_INPUT,NV_OF_BUFFER_FORMAT_GRAYSCALE8);
    s.buffer(s.output,s.columns,s.rows,NV_OF_BUFFER_USAGE_OUTPUT,NV_OF_BUFFER_FORMAT_SHORT2);
    if(cost) s.buffer(s.cost,s.columns,s.rows,NV_OF_BUFFER_USAGE_COST,NV_OF_BUFFER_FORMAT_UINT8);
    const size_t input_bytes=static_cast<size_t>(width)*height, output_bytes=static_cast<size_t>(s.columns)*s.rows*4;
    s.reserve(input_bytes); cuda_check(cuMemHostAlloc(&s.host_input,input_bytes,0));
    s.reserve(output_bytes); cuda_check(cuMemHostAlloc(&s.host_output,output_bytes,0));
    if(cost) { s.reserve(output_bytes/4); cuda_check(cuMemHostAlloc(&s.host_cost,output_bytes/4,0)); }
    return 0;
    CATCH
}
EXPORT int cephvr_nvof_baseline(Session* s,const void* pixels) {
    TRY s->current(); if(s->pending || s->has_baseline) throw std::runtime_error("baseline requires reset/completion");
    s->upload(s->previous,pixels); return 0; CATCH
}
EXPORT int cephvr_nvof_pair(Session* s,const void* pixels) {
    TRY s->current(); if(s->pending || !s->has_baseline) throw std::runtime_error("pair requires completed baseline");
    s->upload(1-s->previous,pixels); s->pair=true;
    NV_OF_EXECUTE_INPUT_PARAMS input{}; input.inputFrame=s->inputs[s->previous].handle;
    input.referenceFrame=s->inputs[1-s->previous].handle;
    input.disableTemporalHints=(!s->hints || s->first_pair)?NV_OF_TRUE:NV_OF_FALSE;
    NV_OF_EXECUTE_OUTPUT_PARAMS output{}; output.outputBuffer=s->output.handle; output.outputCostBuffer=s->cost.handle;
    of_check(s->api.nvOFExecute(s->flow,&input,&output));
    s->download(s->output,s->host_output,static_cast<size_t>(s->columns)*4);
    if(s->cost.handle) s->download(s->cost,s->host_cost,s->columns);
    return 0; CATCH
}
EXPORT int cephvr_nvof_query(Session* s) { TRY return s->complete()?1:0; CATCH }
EXPORT int cephvr_nvof_reset(Session* s) {
    TRY if(!s->complete()) throw std::runtime_error("reset before completion"); s->has_baseline=false; s->first_pair=true; return 0; CATCH
}
EXPORT int cephvr_nvof_view(Session* s,void** flow,void** cost) {
    TRY if(s->pending) throw std::runtime_error("readback before completion"); *flow=s->host_output; *cost=s->host_cost; return 0; CATCH
}
EXPORT int cephvr_nvof_close(Session* s) { TRY s->destroy(); delete s; return 0; CATCH }
