#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
********************************************
Created on Tue Jul 23 15:09:19 2019
by
Chamara Rajapakshe
(cpn.here@umbc.edu)
********************************************

- This example code can aggregate MODIS level 2 data for a given set of variables
  and statistics (min, max, mean, SD).
- This is an intermediate version. Functionalities/usages of each object/function
  are described inside themselves including the directions for future implementations. 
- 3 Main classes
  (1) MODIS_Level2 => To handle MODIS_Level2 data
  (2) MODIS_L2toL3 => To perform L2 to L3 aggregation
  (3) MODIS_level3 => To handle aggregated L3 data / read original L3 data
-----------------------------------------------------
value_locate(), division() are from MODAgg_daily_mean.py
"""
from netCDF4 import Dataset
from jdcal import gcal2jd
import numpy as np
import time,itertools,datetime,os,sys,fnmatch
import h5py

def value_locate(refx, x):
    """
    VALUE_LOCATE locates the positions of given values within a
    reference array.  The reference array need not be regularly
    spaced.  This is useful for various searching, sorting and
    interpolation algorithms.
    The reference array should be a monotonically increasing or
    decreasing list of values which partition the real numbers.  A
    reference array of NBINS numbers partitions the real number line
    into NBINS+1 regions, like so:
        REF:           X[0]         X[1]   X[2] X[3]     X[NBINS-1]
        <----------|-------------|------|---|----...---|--------------->
        INDICES:  -1           0          1    2       3        NBINS-1
        VALUE_LOCATE returns which partition each of the VALUES falls
        into, according to the figure above.  For example, a value between
        X[1] and X[2] would return a value of 1.  Values below X[0] return
        -1, and above X[NBINS-1] return NBINS-1.  Thus, besides the value
        of -1, the returned INDICES refer to the nearest reference value
        to the left of the requested value.

        Example:
            >>> refx = [2, 4, 6, 8, 10]
            >>> x = [-1, 1, 2, 3, 5, 5, 5, 8, 12, 30]
            >>> print value_locate(refx, x)
            array([-1, -1,  0,  0,  1,  1,  1,  3,  4,  4])

            This implementation is likely no the most efficient one, as there
            is
            a loop over all x, which will in practice be long. As long as x is
            shorter than 1e6 or so elements, it should still be fast (~sec).

    """

    refx = np.array(refx)
    x = np.array(x)
    loc = np.zeros(len(x), dtype='int')

    for i in np.arange(len(x)):
        ix = x[i]
        ind = ((refx - ix) <= 0).nonzero()[0]
        if len(ind) == 0:
            loc[i] = -1
        else: loc[i] = ind[-1]

    return loc

def division(n, d):

    div = np.zeros(len(d))
    for i in np.arange(len(d)):
        if d[i] >0:
          div[i]=n[i]/d[i]
        else: div[i]=None 

    return div

def readEntry(key,ncf):
    ncf.variables[key][:]
    rdval=ncf.variables[key][:]
    scale=ncf.variables[key].getncattr('scale_factor')
    offst=ncf.variables[key].getncattr('add_offset')
    return (rdval+offst)*scale
def day_of_year(yr,mn,dy):
    '''
    yr,mn,dy (int)
    '''
    JD01, JD02 = gcal2jd(yr,1,1)
    JD1, JD2 = gcal2jd(yr,mn,dy)
    JD = np.int((JD2+JD1)-(JD01+JD02) + 1)
    return JD

class MODIS_Level2(object):
    '''
    To handle MODIS_Level2 data.
     - So far, only read HDF files in readHDF() function.
     - If needed, additional functions could be added for data representations, etc.
    '''
    def __init__(self,variables):
        '''
        variables (Dictionary): Selected variables to perform computations 
            ex. variables={'Acronym1':('Full_name1','units1'),...}
        '''
        self.var=variables
        return
    def readHDF(self,MYD03,MYD06):
        '''
        MOD06,MOD03: Filenames including the full path.
        Returns:
            latitude,longitude: arrays
            data: Dictionary contains all the variables that had been given to read in.
        '''
        data={}
        myd06 = Dataset(MYD06, "r")
        CM1km = readEntry('Cloud_Mask_1km',myd06)             #Cloud mask
        data['CM'] = (np.array(CM1km[:,:,0],dtype='byte') & 0b00000110) >>1
        #Read all the other specified variables
        for key in self.var:
            data[key]=readEntry(self.var[key][0],myd06)
        
        myd03 = Dataset(MYD03, "r")
        latitude = myd03.variables["Latitude"][:,:] # Reading Specific Variable 'Latitude'.
        latitude = np.array(latitude).byteswap().newbyteorder() # Addressing Byteswap For Big Endian Error.
        longitude = myd03.variables["Longitude"][:,:] # Reading Specific Variable 'Longitude'.
        longitude = np.array(longitude).byteswap().newbyteorder() # Addressing Byteswap For Big Endian Error.
        return latitude,longitude,data
            
class MODIS_L2toL3(object):
    '''
    Reads MODIS level-2 products and compute given statistics
    '''
    def __init__(self,variables,stats,start,l3product='D3'):
        '''
        variables (Dictionary): {'Acronym1':('Full_name1','units1'),...}
        stats (String array): ['mean','stdd','min','max'] or any combination
        start:
            if l3product='D3' => Date ex. '01/01/2008'
            [NOT IMPLEMENTED]if l3product='E3' => Starting date ex. '01/01/2008' (eight days from the given date will considered)
            [NOT IMPLEMENTED]if l3product='M3' => Month ex. '01/2008'
        l3product (String): 'D3','E3','M3' for daily, eight-day and monthly
        '''
        self.variables=variables
        self.stats=stats
        self.start=start
        self.l3product=l3product
    def Aggregate(self,MOD03_path,MOD06_path,fname_ap=None):
        '''
        - Defines self.l3name: level-3 output file name.
        - Defines self.M (Object) which contains all the computed statistics and variables. 
        fname_ap (string): 'a_string_to_append_to_the_L3_output_file'
        '''
        dt=self.start.split('/')
        yr = [int(dt[2])]
        mn = [int(dt[0])] #np.arange(1,13)  #[1]
        dy = [int(dt[1])] #np.arange(1,32) # [1] #np.arange(1,31)
        # latitude and longtitude boundaries of level-3 grid
        if fname_ap is None:
            self.l3name='MOD08_'+self.l3product+'A{:04d}{:03d}'.format(yr[0],day_of_year(yr[0],mn[0],dy[0]))
        else:
            self.l3name='MOD08_'+self.l3product+'A{:04d}{:03d}'.format(yr[0],day_of_year(yr[0],mn[0],dy[0]))+fname_ap
        lat_bnd = np.arange(-90,91,1)
        lon_bnd = np.arange(-180,180,1)
        nlat = 180
        nlon = 360
    
        '''
        Initializations (Both variables and functions for multiple statistics)
        ***************************************************************************
        Since ONLY the user-specified statistics have to be computed, to avoid conditioning (using if statements)
        inside the for loop, separate functions are defined.
        Memory allocation and computations are only be done for the requested variables
        (any combination of variables ex. CTP,CTT,COT,CER,etc.) and statistics
        (any combination of min,max,mean,stdd).
        '''    
        M=Memory() # An empty object to store variables
        M.TOT_pix      = np.zeros(nlat*nlon)#To compute CF 
        M.CLD_pix      = np.zeros(nlat*nlon)#Will be needed for all others including CF
#        M.CF = {'CF':np.zeros(nlat*nlon),'min':np.zeros(nlat*nlon),'max':np.zeros(nlat*nlon)}
        
        
        #mean and stdd (Initialization)
        #Initialization of the variables that'd be required to calculate mean/stdd (or both) if the user
        #specified to compute either mean or stdd or both
        if 'mean' in self.stats or 'stdd' in self.stats:
            M.XXX_pix={}
            for key in self.variables:
                M.XXX_pix[key]=np.zeros(nlat*nlon)
        if 'stdd' in self.stats:
            M.XXX_pixSq=M.XXX_pix # For Stdd
        #Min and Max (Initialization) 
        #Initialization of the variables that'd be required to calculate min/max (or both) if the user
        #specified to compute either min or max or both
        if 'min' in self.stats:
            M.mnx['min']={}
            M.stt['min']={}
            for key in self.variables:
                M.mnx['min'][key]=np.zeros(nlat*nlon)+np.inf
        if 'max' in self.stats:
            M.mnx['max']={}
            M.stt['max']={}
            for key in self.variables:
                M.mnx['max'][key]=np.zeros(nlat*nlon)-np.inf
        '''
        ***********************************************************************
        Defining minmax() function depending on the user requirements
        ***********************************************************************
        '''
        # Min and Max computations
        if not(bool(M.mnx)):
            #No min or max are needed
            def minmax(val,j,M):
                pass
        elif len(M.mnx)>1:
            #Both min and max are needed
            def minmax(val,j,M):
                mn,mx=val.min(),val.max()
                if mn<M.mnx['min'][key][j]:
                    M.mnx['min'][key][j]=mn
                if mx>M.mnx['max'][key][j]:
                    M.mnx['max'][key][j]=mx
        elif 'min' in M.mnx:
            #Only min
            def minmax(val,j,M):
                mn=val.min()
                if mn<M.mnx['min'][key][j]:
                    M.mnx['min'][key][j]=mn
        elif 'max' in M.mnx:
            #Only max
            def minmax(val,j,M):
                mx=val.max()
                if mx>M.mnx['max'][key][j]:
                    M.mnx['max'][key][j]=mx
        '''
        ***********************************************************************
        Defining MeanStd() function depending on the user requirements.
        (minmax() function will be called inside MeanStd())
        ***********************************************************************
        '''        
        # Min, max, mean and stdd computations
        if 'stdd' in self.stats:
            #if only stdd
            M.stt['mean'],M.stt['stdd']={},{}# Mean is needed to calculate Std
            def MeanStd(data,j,latlon_index,M):
                #Both mean and stdd
                for key in data:
                    #print(key)
                    val=data[key][np.where(latlon_index == j)]
                    M.XXX_pix[key][j]=M.XXX_pix[key][j]+np.sum(val)
                    M.XXX_pixSq[key][j]=M.XXX_pixSq[key][j]+np.sum(val**2)   
                    minmax(val,j,M)
        elif 'mean' in self.stats:
            #if only mean
            M.stt['mean']={}
            def MeanStd(data,j,latlon_index,M):
                #Only mean
                for key in data:
                    val=data[key][np.where(latlon_index == j)]
                    M.XXX_pix[key][j]=M.XXX_pix[key][j]+np.sum(val)  
                    minmax(val,j,M)
        elif len(M.mnx)>0:
            #No mean,stdd but min or max
            def MeanStd(data,j,latlon_index,M):
                for key in data:
                    val=data[key][np.where(latlon_index == j)]
                    minmax(val,j,M)
        else:
            #if no any stats
            def MeanStd(data,j,latlon_index,M):
                pass
        '''
        ***********************************************************************
        ***********************************************************************
        '''
        '''
        Looping over the files
        ======================
        '''
        #-----------------------------------------------
        tot_F=0 #Total number of file couples read
        self.start=time.time()
        MD=MODIS_Level2(self.variables)
        for y,m,d in  itertools.product(yr,mn, dy):
            #-------------find the MODIS prodcts--------------#
            #date = datetime.datetime(y,m,d)
            JD01, JD02 = gcal2jd(y,1,1)
            JD1, JD2 = gcal2jd(y,m,d)
            JD = np.int((JD2+JD1)-(JD01+JD02) + 1)
            granule_time = datetime.datetime(y,m,d,0,0)
            while granule_time <= datetime.datetime(y,m,d,23,55):  # 23,55
    #            print('granule time:',granule_time)
                MOD03_fp = 'MYD03.A{:04d}{:03d}.{:02d}{:02d}.006.?????????????.hdf'.format(y,JD,granule_time.hour,granule_time.minute)
                MOD06_fp = 'MYD06_L2.A{:04d}{:03d}.{:02d}{:02d}.006.?????????????.hdf'.format(y,JD,granule_time.hour,granule_time.minute)
                MOD03_fn, MOD06_fn =[],[]
                for MOD06_flist in  os.listdir(MOD06_path):
                    if fnmatch.fnmatch(MOD06_flist, MOD06_fp):
                        MOD06_fn = MOD06_flist
                for MOD03_flist in  os.listdir(MOD03_path):
                    if fnmatch.fnmatch(MOD03_flist, MOD03_fp):
                        MOD03_fn = MOD03_flist
                if MOD03_fn and MOD06_fn: # if both MOD06 and MOD03 products are in the directory
                    tot_F+=1
                    Lat,Lon,data = MD.readHDF(MOD03_path+MOD03_fn,MOD06_path+MOD06_fn)
                    CM=data['CM'].ravel()
                    del data['CM'] #CM is not a final product
                    for key in data:
                        data[key]=data[key].ravel()    
                    Lat=Lat.ravel()
                    Lon=Lon.ravel()
                    lat_index = value_locate(lat_bnd,Lat)
                    lon_index = value_locate(lon_bnd,Lon)
                    latlon_index = lat_index*nlon + lon_index
                    latlon_index_unique = np.unique(latlon_index)
                    
                    for i in np.arange(latlon_index_unique.size):
                        j=latlon_index_unique[i]
                        M.TOT_pix[j] = M.TOT_pix[j]+np.sum(CM[np.where(latlon_index == j)]>=0)
                        M.CLD_pix[j] = M.CLD_pix[j]+np.sum(CM[np.where(latlon_index == j)]<=1)
                        #To calculate other variables and statistics---------------------------
                        MeanStd(data,j,latlon_index,M)
                        #-------------------------------------------------------------------
                    

                granule_time += datetime.timedelta(minutes=5)
    
        #Cloud fractions
        M.total_cloud_fraction  =  division(M.CLD_pix,M.TOT_pix).reshape([nlat,nlon])
        M.pixel_count = M.CLD_pix.reshape([nlat,nlon])
        #The other statistics for all the user specified variables
        for key in data:
            for st in M.stt:
                if st == 'stdd':
                    M.stt['mean'][key]=division(M.XXX_pix[key],M.CLD_pix).reshape([nlat,nlon])
                    #stdd=np.sqrt(<Xi^2>-<X>^2)
                    M.stt[st][key]=np.sqrt(division(M.XXX_pixSq[key],M.CLD_pix).reshape([nlat,nlon])-M.stt['mean'][key]**2)
                elif st == 'mean':
                    M.stt[st][key]=division(M.XXX_pix[key],M.CLD_pix).reshape([nlat,nlon])
                if st == 'min' or st == 'max':
                    M.stt[st][key]=M.mnx[st][key].reshape([nlat,nlon])
        self.M=M
        self.lat_bnd=lat_bnd
        self.lon_bnd=lon_bnd
        
class Memory: pass
class MODIS_level3(object):
    '''
    To handle MODIS level3 data.
    Reading real MODIS level3 data will be implemented later.
    '''
    def __init__(self,filename=None,path=None):
        '''
        To save/read aggregated data.
        To save:
            filename,path=None; use self.save_level3_hdf5()
        To read:
            Give filename (and path) to the file.
            Then use self.get()
        '''
        self.note='Level2_to_level3_aggregated'
        if path is not None:
            self.fn=path+filename
        else:
            self.fn=filename
    def save_level3_hdf5(self,Agg):
        '''
        To save aggregated data products.
        Agg: MODIS_L2toL3 object
        '''
        self.MODIS_L2toL3=Agg
        self.fname=Agg.l3name
        ff=h5py.File(self.fname+'.hdf5','w')
        self.addGridEntry(ff,'CF','Fraction','Cloud_Fraction',Agg.M.total_cloud_fraction)
        self.addGridEntry(ff,'PC','Count','Pixel_Count',Agg.M.pixel_count)
        for key in Agg.variables:
            for st in Agg.M.stt:
                self.addGridEntry(ff, key+'_'+st, Agg.variables[key][1], Agg.variables[key][0]+'_'+self.get_long_name(st), \
                                  Agg.M.stt[st][key])
        PC=ff.create_dataset('lat_bnd',data=Agg.lat_bnd)
        PC.attrs['units']='degrees'
        PC.attrs['long_name']='Latitude_boundaries'    

        PC=ff.create_dataset('lon_bnd',data=Agg.lon_bnd)
        PC.attrs['units']='degrees'
        PC.attrs['long_name']='Longitude_boundaries'    
        ff.close()
        print(self.fname+'.hdf5 Saved!')
                    
    def get_long_name(self,st):
        '''
        Returns long formal name of the statistc when the shorten form is given.
        st (string): 'min', 'max', 'Mean', 'stdd'
        '''
        listt={'min':'Minimum','max':'Maximum','mean':'Mean','stdd':'Standard_Deviation'}
        return listt[st]
    def get_stat(self,var,stat):
        '''
        To read a statistic
        '''
        f=h5py.File(self.fn,'r')
        val=f[var+'_'+stat][:]
        f.close()
        return val   
                
    def addGridEntry(self,f,name,units,long_name,data):
        '''
        f:h5py.File()
        -------------------------------------
        Ex.
        self.addGridEntry(f,'CF','Fraction','Cloud_Fraction',total_cloud_fraction)
        '''
        PCentry=f.create_dataset(name,data=data)
        PCentry.dims[0].label='lat_bnd'
        PCentry.dims[1].label='lon_bnd'
        PCentry.attrs['units']=units
        PCentry.attrs["long_name"]=long_name


if __name__=='__main__':
    fname_ap='.test22'# A string to append to the final output file.
    start='01/01/2008'# Starting date
    
    '''
    Selecting variables and statistics
    ==================================
    variables: Dictionary
        ex. variables={'short_name':('MODIS_L2_variable_name','units')}
    stats: String array
        ex. stats=['mean','max','stdd','min'] # stdd-STandarD Deviation
        ex. stats=['mean','max']
    ONLY selected variables and statistics will be computed.
    '''
    variables={'CTP':('cloud_top_pressure_1km','hPa'),'CTT':('cloud_top_temperature_1km','K')}
    stats = ['mean', 'max', 'stdd','min']

    '''
    File paths
    ==========
    '''
    MOD03_path='/umbc/xfs1/jianwu/users/charaj1/CMAC/MODIS-Aggregation/input-data/MYD03/'
    MOD06_path='/umbc/xfs1/jianwu/users/charaj1/CMAC/MODIS-Aggregation/input-data/MYD06/'
    #MOD03_path = '/umbc/xfs1/cybertrn/common/Data/Satellite_Observations/MODIS/MYD03/'
    #MOD06_path = '/umbc/xfs1/cybertrn/common/Data/Satellite_Observations/MODIS/MYD06_L2/'

    #--------------------------------------------------------------------------
    Agg=MODIS_L2toL3(variables, stats,start) # Creating an object with the given specifications
    Agg.Aggregate(MOD03_path,MOD06_path,fname_ap=fname_ap) # Performing the computations
    
    # Saving level 3 files
    L3=MODIS_level3()
    L3.save_level3_hdf5(Agg)