#!/usr/bin/env python3

#
#Assumes the companion scripts are in the same directory
#Load generic Python Modules
import argparse #parse arguments
import sys
import getopt
import os
import re
import glob
import shutil
import subprocess
import numpy as np
from netCDF4 import Dataset


#===========
from amesgcm.Ncdf_wrapper import Ncdf
from amesgcm.FV3_utils import tshift,daily_to_average,daily_to_diurn,get_trend_2D
from amesgcm.Script_utils import prYellow,prCyan,prRed,find_tod_in_diurn,FV3_file_type,filter_vars
#==========


#======================================================
#                  ARGUMENTS PARSER
#======================================================
parser = argparse.ArgumentParser(description="""\033[93m MarsFiles files manager. Used to convert Legacy GCM to FV3 format \n \033[00m""",
                                formatter_class=argparse.RawTextHelpFormatter)

parser.add_argument('input_file', nargs='+',
                                help='***.nc file or list of ***.nc files ')

parser.add_argument('-fv3','--fv3', nargs='+',
                    help="""Produce FV3's diurn, average and daily files from Legacy outputs  \n"""
                        """> Usage: MarsFiles.py LegacyGCM*.nc -fv3 fixed average  \n"""
                        """> Available options are: 'fixed'  : static fields (e.g topography) \n"""
                        """                         'average': 5 sol averages  \n"""
                        """                         'daily'  : 5 sol contineuous  \n"""
                        """                         'diurn'  : 5 sol average for each time of the day \n"""
                        """\033[00m""")

parser.add_argument('-c','--combine', action='store_true',
                    help="""Combine a sequence of similar files as a single file\n"""
                        """> Usage: MarsFiles.py *.atmos_average.nc --combine \n"""
                        """> Works with Legacy, fixed, average, daily and diuRn files\n"""
                        """ \n""")
                        
parser.add_argument('-t','--tshift', action='store_true',
        help="""Apply timeshift of atmos_diurn files\n"""
            """> Usage: MarsFiles.py *.atmos_diurn.nc --tshift \n"""
            """> Works with diurn files only, \n"""
            """> Can also process vertically interpolated diurn files \n"""
            """>      e.g. ***_diurn_P.nc \n"""
            """ \n""")        
            
parser.add_argument('-ba','--bin_average',nargs='?',const=5, type=int, #Default is 5 sols
                    help="""Bin FV3's 'atmos_daily' files as 'atmos_average' Usefull after computation of high-level fields \n"""
                        """> Usage: MarsFiles.py *.atmos_daily.nc -ba          (default, bin 5 days)\n"""
                        """>        MarsFiles.py *.atmos_daily_pstd.nc -ba 10  (bin 10 days)\n"""
                        """\033[00m""")            
             
parser.add_argument('-bd','--bin_diurn', action='store_true', 
                    help="""Bin FV3's 'atmos_daily' files as 'atmos_diurn' May be used jointly with --bin_average\n"""
                        """> Usage: MarsFiles.py *.atmos_daily.nc -bd             (default, 5 days bin) \n"""
                        """>        MarsFiles.py *.atmos_daily_pstd.nc -bd -ba 10 (bin 10 days)\n"""
                        """>        MarsFiles.py *.atmos_daily_pstd.nc -bd -ba 1  (no binning, similar to raw Legacy output)\n"""
                        """\033[00m""")    

 
parser.add_argument('-hpf','--high_pass_filter',nargs='+',type=float,
                    help="""Temporal filtering utilities, including: low, high, and band pass filters \n"""
                         """> Use '--no_trend' flag  to  keep amplitudes only (data is always detrended before filtering)  \n"""
                         """     (-hpf)  --high_pass_filter sol_min          \n"""
                         """     (-lpf)  --low_pass_filter  sol_max          \n"""
                         """     (-bpf)  --band_pass_filter sol_min sol max  \n"""
                         """> Usage: MarsFiles.py *.atmos_daily.nc -bpf 0.5 10. --no_trend    \n"""
                        """\033[00m""")                        
                        
parser.add_argument('-lpf','--low_pass_filter', nargs='+',type=float,help=argparse.SUPPRESS) #same as  --hpf but without the instructions
parser.add_argument('-bpf','--band_pass_filter', nargs='+',help=argparse.SUPPRESS) #same as --hpf but without the instructions
parser.add_argument('-no_trend','--no_trend',action='store_true',help=argparse.SUPPRESS) #do not include trend 


parser.add_argument('-hpk','--high_pass_zonal',nargs='+',type=int,
                    help="""Spatial filtering utilities, including: low, high, and band pass filters \n"""
                         """> Use '--no_trend' flag  to  keep amplitudes only (data is always detrended before filtering)  \n"""
                         """     (-hpk)  --high_pass_zonal kmin          \n"""
                         """     (-lpk)  --low_pass_zonal  kmax          \n"""
                         """     (-bpk)  --band_pass_zonal kmin kmax  \n"""
                         """> Usage: MarsFiles.py *.atmos_daily.nc -lpk 20 --no_trend    \n"""
                        """\033[00m""")                        
                        
parser.add_argument('-lpk','--low_pass_zonal', nargs='+',type=int,help=argparse.SUPPRESS) #same as  --hpf but without the instructions
parser.add_argument('-bpk','--band_pass_zonal', nargs='+',help=argparse.SUPPRESS) #same as --hpf but without the instructions

                        
parser.add_argument('-include','--include',nargs='+',
                     help="""For data reduction, filtering, time-shift, only include listed variables. Dimensions and 1D variables are always included \n"""
                         """> Usage: MarsFiles.py *.atmos_daily.nc -ba --include ps ts ucomp    \n"""
                         """\033[00m""")      
                                                
parser.add_argument('--debug',  action='store_true', help='Debug flag: release the exceptions')



#Use ncks or internal method to concatenate files
#cat_method='ncks'
cat_method='internal'
def main():
    file_list=parser.parse_args().input_file
    cwd=os.getcwd()
    path2data=os.getcwd()
    
    if parser.parse_args().fv3 and parser.parse_args().combine:
        prRed('Use --fv3 and --combine sequentially to avoid ambiguity ')
        exit()
        
    #===========================================================================
    #=============  Conversion Legacy > FV3 by Richard U. and Alex. K.==========
    #===========================================================================   
        
        
    #=======Convert to FV3================
    if parser.parse_args().fv3:
        for irequest in parser.parse_args().fv3:
            if irequest not in ['fixed','average','daily','diurn'] :
                prRed(irequest +""" is not available, select 'fixed', 'average', 'daily', or 'diurn'""")
    #argument definitions:
        
        do_multi= False
        do_1year= False #Used with LegacyGCM_1year.nc'
    
        #Get files to process
        histlist=[]
        for filei in file_list:
            if not ('/' in filei):
                histlist.append(path2data+'/'+filei)
            else:
                histlist.append(filei)
        fnum = len(histlist)
        if fnum >= 0:do_multi = True #TODO why not 1?
    
        try:
            hist1year= path2data+'/LegacyGCM_1year.nc'
            file1year= Dataset(hist1year,'r',format='NETCDF4_CLASSIC')
            do_1year = True
        except:
            hist1year= None
            do_1year = False
    
        lsmin = None
        lsmax = None
    
        if do_multi:
            for f in histlist:
                histname = os.path.basename(f)
                ls_l = histname[-12:-9]
                ls_r = histname[-6:-3]
                if lsmin is None:
                    lsmin=ls_l
                else:
                    lsmin = str(min(int(lsmin),int(ls_l))).zfill(3)
                if lsmax is None:
                    lsmax=ls_r
                else:
                    lsmax = str(max(int(lsmax),int(ls_r))).zfill(3)
                a=make_FV3_files(f,parser.parse_args().fv3,True,cwd)
                   
    #===========================================================================
    #=============  Append netcdf files along the 'time' dimension =============
    #===========================================================================
    elif parser.parse_args().combine:
        prYellow('Using %s method for concatenation'%(cat_method))
        #TODO Use ncks if it is available (not tested yet)
        if cat_method=='ncks':
            subprocess.check_call('ncks --version',shell=True,stdout=open(os.devnull, "w"), stderr=open(os.devnull, "w"))
            #now cat together the files
            newfavg="Ls"+lsmin+"_Ls"+lsmax+".atmos_average.nc"
            newfdai="Ls"+lsmin+"_Ls"+lsmax+".atmos_daily.nc"
            newfdiu="Ls"+lsmin+"_Ls"+lsmax+".atmos_diurn.nc"
            tempdir=os.path.join(cwd,'temp')
            os.makedirs(tempdir, exist_ok=True)
            os.chdir(tempdir)
    
            catavg = "ncrcat ../*.atmos_average.nc "+"00000.atmos_average.nc"
            catdai = "ncrcat ../*.atmos_daily.nc "+"00000.atmos_daily.nc"
            catdiu = "ncrcat ../*.atmos_diurn.nc "+"00000.atmos_diurn.nc"
            p = subprocess.Popen(catavg, universal_newlines=True, shell=True)
            p.wait()
            p = subprocess.Popen(catdai, universal_newlines=True, shell=True)
            p.wait()
            p = subprocess.Popen(catdiu, universal_newlines=True, shell=True)
            p.wait()
            os.chdir(cwd)
            p = subprocess.run('rm -f Ls*.nc', universal_newlines=True, shell=True)
            p = subprocess.run('mv temp/*.nc .', universal_newlines=True, shell=True)
            p = subprocess.run('rm -rf temp/', universal_newlines=True, shell=True)
            if do_1year:
                a=make_FV3_files(hist1year,cwd)
        #=================================        
        elif cat_method=='internal':
            #Get files to process
            histlist=[]
            for filei in file_list:
                #Add path unless full path is provided
                if not ('/' in filei):
                    histlist.append(path2data+'/'+filei)
                else:
                    histlist.append(filei)
                    
            fnum = len(histlist)
            #Easy case: merging *****.fixed.nc means delete all but the first file:
            if file_list[0][5:]=='.fixed.nc' and fnum>=2:
                rm_cmd='rm -f '
                for i in range(1,fnum):
                    rm_cmd+=' '+histlist[i]   
                p = subprocess.run(rm_cmd, universal_newlines=True, shell=True)
                prCyan('Cleaned all but '+file_list[0])
                exit()
            #=========    
            fnum = len(histlist)
            prCyan('Merging %i files, starting with %s ...'%(fnum,file_list[0]))
            
            #This section is to exclude any variable, if the --include option is used:
            if parser.parse_args().include:
                f=Dataset(file_list[0],'r')
                exclude_list = filter_vars(f,parser.parse_args().include,giveExclude=True) # variable to exclude
                f.close()
            else: 
                exclude_list=[]
            
            #this is a temporaty file ***_tmp.nc
            file_tmp=histlist[0][:-3]+'_tmp'+'.nc'
            Log=Ncdf(file_tmp,'Merged file')
            Log.merge_files_from_list(histlist,exclude_var=exclude_list)
            Log.close()
            
            #=====Delete files that have been combined====
            
            #Rename merged file  LegacyGCM_LsINI_LsEND.nc or first files of the list (e.g 00010.atmos_average.nc)
            if file_list[0][:12]=='LegacyGCM_Ls':
                ls_ini=file_list[0][12:15]
                ls_end=file_list[-1][18:21]
                fileout='LegacyGCM_Ls%s_Ls%s.nc'%(ls_ini,ls_end)
                
            else:
                fileout=histlist[0]
            
            #---Assemble 'remove' and 'move' commands to execute-----    
            rm_cmd='rm -f '
            for ifile in histlist:
                rm_cmd+=' '+ifile    
            cmd_txt='mv '+file_tmp+' '+fileout 
            p = subprocess.run(rm_cmd, universal_newlines=True, shell=True)
            p = subprocess.run(cmd_txt, universal_newlines=True, shell=True)
            prCyan(fileout +' was merged')
            
#===============================================================================    
#================= Tshift implementation by Victoria H. ===========================
#===============================================================================
    elif parser.parse_args().tshift:
        for filei in file_list:
            #Add path unless full path is provided
            if not ('/' in filei):
                fullnameIN = path2data + '/' + filei
            else:
                fullnameIN=filei
            fullnameOUT = fullnameIN[:-3]+'_T'+'.nc'

            fdiurn = Dataset(fullnameIN, 'r', format='NETCDF4_CLASSIC')
            fnew = Ncdf(fullnameOUT) # define a Ncdf object from the Ncdf wrapper module
            #Copy some dimensions from the old file to the new file
            fnew.copy_all_dims_from_Ncfile(fdiurn)

            #find time of day variable name
            tod_name=find_tod_in_diurn(fdiurn)
            _,zaxis=FV3_file_type(fdiurn)

            # Copy some variables from the old file to the new file
            fnew.copy_Ncaxis_with_content(fdiurn.variables['lon'])
            fnew.copy_Ncaxis_with_content(fdiurn.variables['lat'])

            #Only create a vertical axis if the original file contains 3D fields
            if zaxis in fdiurn.dimensions.keys():
                fnew.copy_Ncaxis_with_content(fdiurn.variables[zaxis])

            fnew.copy_Ncaxis_with_content(fdiurn.variables['time'])
            fnew.copy_Ncaxis_with_content(fdiurn.variables[tod_name])
            #Only copy areo if existing in the original file:
            if 'areo' in  fdiurn.variables.keys():
                fnew.copy_Ncvar(fdiurn.variables['areo'])

            # read 4D field and do time shift
            tod_in=np.array(fdiurn.variables[tod_name])
            longitude = np.array(fdiurn.variables['lon'])
            var_list = filter_vars(fdiurn,parser.parse_args().include) # get all variables

            for ivar in var_list:
                prCyan("Processing: %s ..."%(ivar))
                varIN = fdiurn.variables[ivar][:]
                vkeys = fdiurn.variables[ivar].dimensions
                if (len(vkeys) == 4):
                    ilat = vkeys.index('lat')
                    ilon = vkeys.index('lon')
                    itime = vkeys.index('time')
                    itod = vkeys.index(tod_name)
                    newvar = np.transpose(varIN,(ilon,ilat,itime,itod))
                    newvarOUT = tshift(newvar,lon=longitude,timex=tod_in)
                    varOUT = np.transpose(newvarOUT, (2,3,1,0))            
                    fnew.log_variable(ivar,varOUT,['time',tod_name,'lat','lon'],fdiurn.variables[ivar].long_name,fdiurn.variables[ivar].units)
                if (len(vkeys) == 5):
                    ilat = vkeys.index('lat')
                    ilon = vkeys.index('lon')
                    iz  = vkeys.index(zaxis)
                    itime = vkeys.index('time')
                    itod = vkeys.index(tod_name)
                    newvar = np.transpose(varIN,(ilon,ilat,iz,itime,itod))
                    newvarOUT = tshift(newvar,lon=longitude,timex=tod_in)
                    varOUT = np.transpose(newvarOUT,(3,4,2,1,0))
                    fnew.log_variable(ivar,varOUT,['time',tod_name,zaxis,'lat','lon'],fdiurn.variables[ivar].long_name,fdiurn.variables[ivar].units)
            fnew.close()
            fdiurn.close()    
            
            
    #===========================================================================
    #===============  Bin an atmos_daily file to atmos_average =================
    #===========================================================================
    elif parser.parse_args().bin_average and not parser.parse_args().bin_diurn: 
        nday=parser.parse_args().bin_average
        for filei in file_list:
            #Add path unless full path is provided
            if not ('/' in filei):
                fullnameIN = path2data + '/' + filei
            else:
                fullnameIN=filei
            fullnameOUT = fullnameIN[:-3]+'_to_average'+'.nc'

            fdaily = Dataset(fullnameIN, 'r', format='NETCDF4_CLASSIC')
            var_list = filter_vars(fdaily,parser.parse_args().include) # get all variables
            
            time_in=fdaily.variables['time'][:]
            Nin=len(time_in)
            
            dt_in=time_in[1]-time_in[0]
            iperday=int(np.round(1/dt_in))
            combinedN=int(iperday*nday)
            
            N_even=Nin//combinedN
            N_left=Nin%combinedN

            if N_left!=0:
                prYellow('***Warning*** requested  %i sols bin period. File has %i timestep/sols and %i/(%i x %i) is not a round number'%(nday,iperday,Nin,nday,iperday))
                prYellow('    Will use %i  bins of (%i x %i)=%i timesteps (%i) and discard %i timesteps'%(N_even,nday,iperday,combinedN,N_even*combinedN,N_left)) 
        

            fnew = Ncdf(fullnameOUT) # define a Ncdf object from the Ncdf wrapper module
            #Copy all dims but time from the old file to the new file
            fnew.copy_all_dims_from_Ncfile(fdaily,exclude_dim=['time'])
            

            #-----Calculate and log the new time array -----
            fnew.add_dimension('time',None)
            time_out=daily_to_average(time_in[:],dt_in,nday)
            fnew.log_axis1D('time',time_out,'time',longname_txt="sol number",units_txt='days since 0000-00-00 00:00:00',cart_txt='T')
        
                
            #Loop over all variables in file
            for ivar in var_list:
                varNcf     = fdaily.variables[ivar]
                
                if 'time' in varNcf.dimensions :     
                    prCyan("Processing: %s ..."%(ivar))
                    var_out=daily_to_average(varNcf[:],dt_in,nday)
                    fnew.log_variable(ivar,var_out,varNcf.dimensions,varNcf.long_name,varNcf.units)
                else:
                    if  ivar in ['pfull', 'lat', 'lon','phalf','pk','bk','pstd','zstd','zagl']:
                        prCyan("Copying axis: %s..."%(ivar))
                        fnew.copy_Ncaxis_with_content(fdaily.variables[ivar])
                    else: 
                        prCyan("Copying var: %s..."%(ivar))   
                        fnew.copy_Ncvar(fdaily.variables[ivar]) 
            fnew.close()

    #===========================================================================
    #===============  Bin an atmos_daily file to atmos_diurn ===================
    #===========================================================================
    elif parser.parse_args().bin_diurn: 
        #Use defaut binning period of 5 days  
        if parser.parse_args().bin_average is None:
            nday=5
        else:
            nday=parser.parse_args().bin_average
                
        for filei in file_list:
            #Add path unless full path is provided
            if not ('/' in filei):
                fullnameIN = path2data + '/' + filei
            else:
                fullnameIN=filei
            fullnameOUT = fullnameIN[:-3]+'_to_diurn'+'.nc'

            fdaily = Dataset(fullnameIN, 'r', format='NETCDF4_CLASSIC')
            var_list = filter_vars(fdaily,parser.parse_args().include) # get all variables
            
            time_in=fdaily.variables['time'][:]
            Nin=len(time_in)
            
            dt_in=time_in[1]-time_in[0]
            iperday=int(np.round(1/dt_in))

            
            fnew = Ncdf(fullnameOUT) # define a Ncdf object from the Ncdf wrapper module
            #Copy all dims but time from the old file to the new file
            fnew.copy_all_dims_from_Ncfile(fdaily,exclude_dim=['time'])
            
            
            # If no binning is requested, copy time axis as-is
            fnew.add_dimension('time',None)    
            time_out=daily_to_average(time_in[:],dt_in,nday)
            fnew.add_dim_with_content('time',time_out,longname_txt="sol number",units_txt='days since 0000-00-00 00:00:00',cart_txt='T')

            #-----Create new  time of day dimension----
            tod_name='time_of_day_%02d'%(iperday)
            time_tod=np.squeeze(daily_to_diurn(time_in[0:iperday],time_in[0:iperday]))
            tod=np.mod(time_tod*24,24)
            fnew.add_dim_with_content(tod_name,tod,longname_txt="time of day",units_txt="hours since 0000-00-00 00:00:00",cart_txt='N')

       
                
            #Loop over all variables in file
            for ivar in var_list:
                
                varNcf     = fdaily.variables[ivar]
                
                #If time is the dimension (but not just a time array)
                if 'time' in varNcf.dimensions and ivar!='time':   
                    prCyan("Processing: %s ..."%(ivar))
                    dims_in=varNcf.dimensions
                    dims_out=(dims_in[0],)+(tod_name,)+dims_in[1:]
                    var_out=daily_to_diurn(varNcf[:],time_in[0:iperday])
                    if nday!=1:var_out=daily_to_average(var_out,1.,nday) #dt is 1 sol between two diurn timestep
                    fnew.log_variable(ivar,var_out,dims_out,varNcf.long_name,varNcf.units)
                    
                else:
                    
                    if  ivar in ['pfull', 'lat', 'lon','phalf','pk','bk','pstd','zstd','zagl']:
                        prCyan("Copying axis: %s..."%(ivar))
                        fnew.copy_Ncaxis_with_content(fdaily.variables[ivar])
                    elif ivar!='time': 
                        prCyan("Copying var: %s..."%(ivar))   
                        fnew.copy_Ncvar(fdaily.variables[ivar]) 
            fnew.close()


    #===========================================================================
    #========================  Transient wave analysis =========================
    #===========================================================================
    elif parser.parse_args().high_pass_filter or parser.parse_args().low_pass_filter or parser.parse_args().band_pass_filter: 
    
        
        # This functions requires scipy > 1.2.0 , so we only import the package here if needed
        from amesgcm.Spectral_utils import zeroPhi_filter
        
        if parser.parse_args().high_pass_filter:
            btype='high';out_ext='_hpf';nsol=np.asarray(parser.parse_args().high_pass_filter).astype(float)
            if len(np.atleast_1d(nsol))!=1:
                prRed('***Error*** sol_min must be only one value')
                exit()
        if parser.parse_args().low_pass_filter:
            btype='low';out_ext='_lpf';nsol=np.asarray(parser.parse_args().low_pass_filter).astype(float)
            if len(np.atleast_1d(nsol))!=1:
                prRed('sol_max must be only one value')
                exit()
        if parser.parse_args().band_pass_filter:
            btype='band';out_ext='_bpf';nsol=np.asarray(parser.parse_args().band_pass_filter).astype(float)   
            if len(np.atleast_1d(nsol))!=2:
                prRed('Need 2 values: sol_min sol_max')   
                exit()          
        if parser.parse_args().no_trend:out_ext =out_ext+'_no_trend'      
        
        for filei in file_list:
            #Add path unless full path is provided
            if not ('/' in filei):
                fullnameIN = path2data + '/' + filei
            else:
                fullnameIN=filei
            fullnameOUT = fullnameIN[:-3]+out_ext+'.nc'

            fdaily = Dataset(fullnameIN, 'r', format='NETCDF4_CLASSIC')
            
            var_list = filter_vars(fdaily,parser.parse_args().include) # get all variables
            
            time_in=fdaily.variables['time'][:]
            
            dt=time_in[1]-time_in[0]
            
            #Check if the frequency domain is allowed 
          
            if any(nn <= 2*dt for nn in nsol):
                prRed('***Error***  min cut-off cannot be smaller than the Nyquist period of 2xdt=%g sol'%(2*dt))
                exit()
                
            fnew = Ncdf(fullnameOUT) # define a Ncdf object from the Ncdf wrapper module
            #Copy all dims but time from the old file to the new file
            fnew.copy_all_dims_from_Ncfile(fdaily)
            
  
            if btype=='low':
                fnew.add_constant('sol_max',nsol,"Low-pass filter cut-off period ","sol")
            elif btype=='high':    
                fnew.add_constant('sol_min',nsol,"High-pass filter cut-off period ","sol")
            elif btype=='band': 
                fnew.add_constant('sol_min',nsol[0],"High-pass filter low cut-off period ","sol")
                fnew.add_constant('sol_max',nsol[1],"High-pass filter high cut-off period ","sol")  
            dt=time_in[1]-time_in[0]
            
            fs=1/(dt) # frequency in sol-1
            if btype =='band':
                # Flip the sols so the low frequency comes first
                low_highcut=1/nsol[::-1]
            else:
                low_highcut=1./nsol
                    
            #Loop over all variables in file
            for ivar in var_list:
                varNcf     = fdaily.variables[ivar]
                
                if 'time' in varNcf.dimensions and ivar not in ['time','areo'] :     
                    prCyan("Processing: %s ..."%(ivar))
                    var_out=zeroPhi_filter(varNcf[:], btype, low_highcut, fs,axis=0,order=4,no_trend=parser.parse_args().no_trend)
                    fnew.log_variable(ivar,var_out,varNcf.dimensions,varNcf.long_name,varNcf.units)
                else:
                    if  ivar in ['pfull', 'lat', 'lon','phalf','pk','bk','pstd','zstd','zagl']:
                        prCyan("Copying axis: %s..."%(ivar))
                        fnew.copy_Ncaxis_with_content(fdaily.variables[ivar])
                    else: 
                        prCyan("Copying var: %s..."%(ivar))   
                        fnew.copy_Ncvar(fdaily.variables[ivar]) 
            fnew.close()

    #===========================================================================
    #========================  Zonal decomposition analysis ====================
    #===========================================================================
    elif parser.parse_args().high_pass_zonal or parser.parse_args().low_pass_zonal or parser.parse_args().band_pass_zonal: 
    
        # This functions requires scipy > 1.2.0 , so we only import the package here if needed
        from amesgcm.Spectral_utils import zonal_decomposition, zonal_construct
        #Load the module
        #init_shtools()
        
        if parser.parse_args().high_pass_zonal:
            btype='high';out_ext='_hpk';nk=np.asarray(parser.parse_args().high_pass_zonal).astype(int)
            if len(np.atleast_1d(nk))!=1:
                prRed('***Error*** kmin must be only one value')
                exit()
        if parser.parse_args().low_pass_zonal:
            btype='low';out_ext='_lpk';nk=np.asarray(parser.parse_args().low_pass_zonal).astype(int)
            if len(np.atleast_1d(nk))!=1:
                prRed('kmax must be only one value')
                exit()
        if parser.parse_args().band_pass_zonal:
            btype='band';out_ext='_bpk';nk=np.asarray(parser.parse_args().band_pass_zonal).astype(int)   
            if len(np.atleast_1d(nk))!=2:
                prRed('Need 2 values: kmin kmax')   
                exit()           
                
        if parser.parse_args().no_trend:out_ext =out_ext+'_no_trend' 
        
        for filei in file_list:
            #Add path unless full path is provided
            if not ('/' in filei):
                fullnameIN = path2data + '/' + filei
            else:
                fullnameIN=filei
            fullnameOUT = fullnameIN[:-3]+out_ext+'.nc'
    
            fname = Dataset(fullnameIN, 'r', format='NETCDF4_CLASSIC')
            
            var_list = filter_vars(fname,parser.parse_args().include) # get all variables
            
            lon=fname.variables['lon'][:]
            lat=fname.variables['lat'][:]
            LON,LAT=np.meshgrid(lon,lat)
            
            dlat=lat[1]-lat[0]
            dx=2*np.pi*3400
            
            #Check if the frequency domain is allowed and display some information 
        
            if any(nn > len(lat)/2 for nn in nk):
                prRed('***Warning***  max wavenumber cut-off cannot be larger than the Nyquist criteria of nlat/2= %i sol'%(len(lat)/2))
            elif btype=='low':
                L_max=(1./nk)*dx
                prYellow('Low pass filter, letting only wavelenght > %g km'%(L_max))
            elif btype=='high':
                L_min=(1./nk)*dx
                prYellow('High pass filter, letting only wavelenght < %g km'%(L_min))                
            elif btype=='band':
                L_min=(1./nk[1])*dx
                L_max=1./max(nk[0],1.e-20)*dx 
                if L_max>1.e20:L_max=np.inf
                prYellow('Band pass filter, letting only %g km < wavelenght < %g km'%(L_min,L_max))                

        
            fnew = Ncdf(fullnameOUT) # define a Ncdf object from the Ncdf wrapper module
            #Copy all dims but time from the old file to the new file
            fnew.copy_all_dims_from_Ncfile(fname)
            
            if btype=='low':
                fnew.add_constant('kmax',nk,"Low-pass filter zonal wavenumber ","wavenumber")
            elif btype=='high':    
                fnew.add_constant('kmin',nk,"High-pass filter zonal wavenumber ","wavenumber")
            elif btype=='band': 
                fnew.add_constant('kmin',nk[0],"Band-pass filter low zonal wavenumber ","wavenumber")
                fnew.add_constant('kmax',nk[1],"Band-pass filter high zonal wavenumber ","wavenumber")  
            
            low_highcut=nk
                    
            #Loop over all variables in file
            for ivar in var_list:
                varNcf     = fname.variables[ivar]
                
                if ('lat' in varNcf.dimensions) and ('lon' in varNcf.dimensions):     
                    prCyan("Processing: %s ..."%(ivar))
                    
                    # Step 1 : detrend the data
                    TREND=get_trend_2D(varNcf[:],LON,LAT,'wmean')
                    # Step 2 : calculate spherical harmonic coefficients
                    COEFF,PSD=zonal_decomposition(varNcf[:]-TREND)
                    # Step 3 : Recompose the variable out of the coefficients
                    VAR_filtered=zonal_construct(COEFF,varNcf[:].shape,btype=btype,low_highcut=low_highcut)
                    #Step 4: add the trend, if request
                    if parser.parse_args().no_trend:
                        var_out=VAR_filtered
                    else:    
                        var_out=VAR_filtered+TREND
                                        
                    fnew.log_variable(ivar,var_out,varNcf.dimensions,varNcf.long_name,varNcf.units)
                else:
                    if  ivar in ['pfull', 'lat', 'lon','phalf','pk','bk','pstd','zstd','zagl','time']:
                        prCyan("Copying axis: %s..."%(ivar))
                        fnew.copy_Ncaxis_with_content(fname.variables[ivar])
                    else: 
                        prCyan("Copying var: %s..."%(ivar))   
                        fnew.copy_Ncvar(fname.variables[ivar]) 
            fnew.close()



            
    else:
        prRed("""Error: no action requested: use 'MarsFiles *nc --fv3 --combine, --tshift, --bin_average, --bin_diurn'""")    


#END of script
        
#*******************************************************************************
#*************Definitions for functions used in this script ********************
#*******************************************************************************
          

def make_FV3_files(fpath,typelistfv3,renameFV3=True,cwd=None):
    '''
    Make FV3-type atmos_average,atmos_daily,atmos_diurn
    Args:
        fpath     : full path to Legacy .nc files
        typelistfv3: e.g['average', 'daily', 'diurn']
        renameFV3 : rename files from Legacy_Lsxxx_Lsyyy.nc to XXXXX.atmos_average.nc folllowing FV3's convention
        cwd       : output path
    Returns:
        atmos_average,atmos_daily,atmos_diurn
    '''
    
    histname = os.path.basename(fpath)
    if cwd is None:
        histdir = os.path.dirname(fpath)
    else:
        histdir = cwd

    histfile = Dataset(fpath,'r',format='NETCDF4_CLASSIC')
    histvars = histfile.variables.keys()
    histdims = histfile.dimensions.keys()
    
    #Convert the first Ls in file to a sol number
    if renameFV3:fdate= '%05i'%(ls2sol_1year(histfile.variables['ls'][0]))

    def proccess_file(newf,typefv3):
        for dname in histdims:
            if dname == 'nlon':
                var=histfile.variables['longitude']
                npvar=var[:]
                newf.add_dim_with_content('lon',npvar,'longitude',getattr(var,'units'),'X')
            elif dname == 'nlat':
                var=histfile.variables['latitude']
                npvar=var[:]
                newf.add_dim_with_content('lat',npvar,'latitude',getattr(var,'units'),'Y')

            elif dname == 'time':
                newf.add_dimension('time',None)
            elif dname == 'ntod' and typefv3=='diurn':
                dim=histfile.dimensions[dname]
                newf.add_dimension('time_of_day_16',dim.size)
            elif dname == 'nlay':
                nlay=histfile.dimensions[dname]
                num =nlay.size
                nump=num+1
                pref=7.01*100  # in Pa
                pk=np.zeros(nump)
                bk=np.zeros(nump)
                pfull=np.zeros(num)
                phalf=np.zeros(nump)
                dsgm=histfile.variables['dsgm'] #TODO not used
                sgm =histfile.variables['sgm']
                pk[0]=0.08/2 #[AK] changed pk[0]=.08 to pk[0]=.08/2, otherwise phalf[0] would be greater than phalf[1]
                #*** NOTE that pk in amesGCM/mars_data/Legacy.fixed.nc was also updated***
                for z in range(num):
                    bk[z+1] = sgm[2*z+2]
                phalf[:]=pk[:]+pref*bk[:] # output in  Pa

                # DEPRECIATED: pfull[:] = (phalf[1:]-phalf[:num])/(np.log(phalf[1:])-np.log(phalf[:num]))
                #First layer
                if pk[0]==0 and bk[0]==0: 
                    pfull[0]=0.5*(phalf[0]+phalf[1])
                else:
                    pfull[0]=(phalf[1]-phalf[0])/(np.log(phalf[1])-np.log(phalf[0]))
                #Rest of layers:   
                pfull[1:] = (phalf[2:]-phalf[1:-1])/(np.log(phalf[2:])-np.log(phalf[1:-1]))

                newf.add_dim_with_content('pfull',pfull,'ref full pressure level','Pa')
                newf.add_dim_with_content('phalf',phalf,'ref half pressure level','Pa')
                newf.log_axis1D('pk',pk,('phalf'),longname_txt='pressure part of the hybrid coordinate',units_txt='Pa',cart_txt='')
                newf.log_axis1D('bk',bk,('phalf'),longname_txt='sigma part of the hybrid coordinate',units_txt='Pa',cart_txt='')
            else:
                dim=histfile.dimensions[dname]
                newf.add_dimension(dname,dim.size)

        #===========END function========

    
    if 'average' in typelistfv3:
        newfname_avg = fdate+'.atmos_average.nc'  #5 sol averages over tod and time
        newfpath_avg = os.path.join(histdir,newfname_avg)
        newfavg = Ncdf(newfpath_avg)
        proccess_file(newfavg,'average')
        do_avg_vars(histfile,newfavg,True,True)
        newfavg.close()
        
    if 'daily' in typelistfv3:
        newfname_daily = fdate+'.atmos_daily.nc'  #daily snapshot output...this is exactly the current output?
        newfpath_daily = os.path.join(histdir,newfname_daily)
        newfdaily = Ncdf(newfpath_daily)
        proccess_file(newfdaily,'daily')
        do_avg_vars(histfile,newfdaily,False,False)
        newfdaily.close()
        
    if 'diurn' in typelistfv3:
        newfname_diurn = fdate+'.atmos_diurn.nc'  #5 sol averages over time only
        newfpath_diurn = os.path.join(histdir,newfname_diurn)
        newfdiurn = Ncdf(newfpath_diurn)
        proccess_file(newfdiurn,'diurn')
        do_avg_vars(histfile,newfdiurn,True,False)
        newfdiurn.close()
        
    if 'fixed' in typelistfv3:
    #Copy Legacy.fixed to current directory 
        cmd_txt='cp '+sys.prefix+'/mars_data/Legacy.fixed.nc '+fdate+'.fixed.nc'
        p = subprocess.run(cmd_txt, universal_newlines=True, shell=True)
        print(cwd+'/'+fdate+'.fixed.nc was copied locally')
    


#Function to perform time averages over all fields
def do_avg_vars(histfile,newf,avgtime,avgtod,Nday=5):
    histvars = histfile.variables.keys()
    for vname in histvars:
        var     = histfile.variables[vname]
        npvar = var[:]
        dims  = var.dimensions
        ndims = npvar.ndim
        vshape= npvar.shape
        ntod  = histfile.dimensions['ntod']
        
        longname_txt=getattr(histfile.variables[vname],'long_name','')
        
        #On some files like the LegacyGCM_Ls*** on the NAS dataportal, the attribute 'long_name' may be mispelled 'longname'
        if longname_txt=='':longname_txt=getattr(histfile.variables[vname],'longname','')
        
        units_txt=getattr(histfile.variables[vname],'units','')
        
        if avgtod:
            newdims  = replace_dims(dims,True)
        elif avgtime:
            newdims  = replace_dims(dims,False)
        else:
            newdims  = replace_dims(dims,True)


        if 'time' in dims:
            tind = dims.index('time')
            tind_new= newdims.index('time')
            numt = histfile.dimensions['time'].size
        #TODO fix time !!
        #now do various time averaging and write to files
        if ndims == 1:
            if vname == 'ls':
                #first check if spans new year
                
                if not np.all(npvar[1:] >= npvar[:-1]):
                    year = 0.
                    for x in range(1,npvar.size):
                        if 350. < npvar[x-1] < 360. and npvar[x] < 10.:
                            year += 1.
                        npvar[x] += 360.*year
                      
                #Create a time array        
                time0=ls2sol_1year(npvar[0])+np.linspace(0,10.,len(npvar)) 
                 
                if avgtime:
                    varnew = np.mean(npvar.reshape(-1,Nday),axis=1)
                    time0 =  np.mean(time0.reshape(-1,Nday),axis=1)

                if not avgtime and not avgtod: #i.e daily file
                    # Solar longitude
                    ls_start = npvar[0]
                    ls_end   = npvar[-1]
                    step     = (ls_end-ls_start)/np.float32(((numt-1)*ntod.size))
                    varnew = np.arange(0,numt*ntod.size,dtype=np.float32)
                    varnew[:] = varnew[:]*step+ls_start
                    
                    #Time
                    step = (ls2sol_1year(ls_end)-ls2sol_1year(ls_start))/np.float32((numt*ntod.size))
                    time0 = np.arange(0,numt*ntod.size,dtype=np.float32)
                    time0[:] = time0[:]*step+ls2sol_1year(ls_start)
                    
                newf.log_axis1D('areo',varnew,dims,longname_txt='solar longitude',units_txt='degree',cart_txt='T')
                newf.log_axis1D('time',time0,dims,longname_txt='sol number',units_txt='days since 0000-00-00 00:00:00',cart_txt='T')#added AK
            else:
                continue
        elif ndims == 4:
            varnew = npvar
            if avgtime:
                varnew = np.mean(npvar.reshape(-1,Nday,vshape[1],vshape[2],vshape[3]),axis=1)
            if avgtod:
                varnew = varnew.mean(axis=1)
            if not avgtime and not avgtod:
                varnew = npvar.reshape(-1,vshape[2],vshape[3])
            #Rename variable    
            vname2,longname_txt2,units_txt2=change_vname_longname_unit(vname,longname_txt,units_txt)
            #AK convert surface pressure from mbar to Pa
            if vname2=='ps':varnew*=100.
            newf.log_variable(vname2,varnew,newdims,longname_txt2,units_txt2)
        elif ndims == 5:
            varnew = npvar
            if avgtime:
                varnew = np.mean(npvar.reshape(-1,Nday,vshape[1],vshape[2],vshape[3],vshape[4]),axis=1)
            if avgtod:
                varnew = varnew.mean(axis=1)
            if not avgtime and not avgtod:
                varnew = npvar.reshape(-1,vshape[2],vshape[3],vshape[4]) 
            #Rename variables   
            vname2,longname_txt2,units_txt2=change_vname_longname_unit(vname,longname_txt,units_txt)
            newf.log_variable(vname2,varnew,newdims,longname_txt2,units_txt2)
        elif vname == 'tloc':
            if avgtime and not avgtod:
                vname2='time_of_day_16'
                longname_txt2='time of day'
                units_txt2='hours since 0000-00-00 00:00:00' 
                # Overwrite tod from ('time_of_day_16', 'lon') to time_of_day_16
                newdims=('time_of_day_16')
                npvar=np.arange(0.75,24,1.5)  # every 1.5 hours, centered at half timestep ? AK
                newf.log_variable(vname2,npvar,newdims,longname_txt2,units_txt2)
                
    return 0

def change_vname_longname_unit(vname,longname_txt,units_txt):
    
    if vname == 'psurf':
        vname = 'ps'
        longname_txt='surface pressure'
        units_txt='Pa'
    elif vname == 'tsurf':
        vname = 'ts'
        longname_txt='surface temperature'
        units_txt='K'
    elif vname=='dst_core_mass':    
        vname = 'cor_mass'
        longname_txt='dust core mass for the water ice aerosol'
        units_txt='kg/kg'
            
    elif vname=='h2o_vap_mass':    
        vname = 'vap_mass'
        longname_txt='water vapor mixing ratio'
        units_txt='kg/kg' 
            
    elif vname=='h2o_ice_mass':    
        vname = 'ice_mass'
        longname_txt='water ice aerosol mass mixing ratio'
        units_txt='kg/kg' 

    elif vname=='dst_mass':    
        vname = 'dst_mass'
        longname_txt='dust aerosol mass mixing ratio'
        units_txt='kg/kg' 

    elif vname=='dst_numb':    
        vname = 'dst_num'
        longname_txt='dust aerosol number'
        units_txt='number/kg' 
            
    elif vname=='h2o_ice_numb':    
        vname = 'ice_num'
        longname_txt='water ice aerosol number'
        units_txt='number/kg'           
    elif vname=='temp':    
        longname_txt='temperature'
        units_txt='K'     
    elif vname=='ucomp':    
        longname_txt='zonal wind'
        units_txt='m/s'
    elif vname=='vcomp':    
        longname_txt='meridional wind'
        units_txt='m/s'                 
    else: 
        #Return original values
        pass
    return vname,longname_txt,units_txt
    
#Function to replace dimensions with fv3 names and remove tod
def replace_dims(dims,todflag):
    newdims = dims
    if 'nlat' in dims:
        newdims = replace_at_index(newdims,newdims.index('nlat'),'lat')
    if 'nlon' in dims:
        newdims = replace_at_index(newdims,newdims.index('nlon'),'lon')
    if 'nlay' in dims:
        newdims = replace_at_index(newdims,newdims.index('nlay'),'pfull')
    if 'ntod' in dims:
        if todflag:
            newdims = replace_at_index(newdims,newdims.index('ntod'),None)
        else:
            newdims = replace_at_index(newdims,newdims.index('ntod'),'time_of_day_16')
    return newdims

def replace_at_index(tup, ix, val):
    if val is None:
        return tup[:ix]+tup[ix+1:]
    else:
        return tup[:ix] + (val,) + tup[ix+1:]


def ls2sol_1year(Ls_deg,offset=True,round10=True):
    '''
    Returns a sol number from the solar longitude.
    Args:
        Ls_deg: solar longitude in degree
        offset : if True, make year starts at Ls 0
        round10 : if True, round to the nearest 10 sols
    Returns:
        Ds :sol number
    ***NOTE***
    For the moment this is consistent with Ls 0->359.99, not for monotically increasing Ls
    '''
    Lsp=250.99   #Ls at perihelion
    tperi=485.35 #Time (in sols) at perihelion
    Ns=668.6     #Number of soils in 1 MY
    e=0.093379   #from GCM: modules.f90
    nu=(Ls_deg-Lsp)*np.pi/180
    E=2*np.arctan(np.tan(nu/2)*np.sqrt((1-e)/(1+e)))
    M=E-e*np.sin(E)
    Ds= M/(2*np.pi)*Ns+tperi
    #====Offset correction======
    if offset:
        #Ds is a float
        if len(np.atleast_1d(Ds))==1:
            Ds-=Ns
            if Ds<0:Ds+=Ns
        #Ds is an array
        else:
            Ds-=Ns
            Ds[Ds<0]=Ds[Ds<0]+Ns
    if round: Ds=np.round(Ds,-1)  #-1 means round to the nearest 10      
    return Ds

if __name__ == "__main__":
    main()
